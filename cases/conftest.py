import itertools
import os
import time
from pathlib import Path

import pytest

from gameqa.accounts import pair_for
from gameqa.bridge import Bridge, redact
from gameqa.config import resolve_path
from gameqa.stendhal import Stendhal
from gameqa.stendhal_ui import StendhalUI

pytest_plugins = ["gameqa.pytest_plugin"]


_CASE_INDEX = itertools.count()


@pytest.fixture
def case_index():
    """本用例在整轮里的序号。用来轮换账号：相邻用例不用同一个账号。

    动机：服务端对同一账号的重复登录会静默踢掉前一个会话，上一条用例的断开若晚于本次登录被处理，
    就会把新会话当成旧的移除（实测复现）。错开账号即可绕开这个时间窗。
    """
    return next(_CASE_INDEX)


@pytest.fixture
def qa_pair(game_config, case_index):
    """本用例使用的（观察者, 目标）账号对。"""
    return pair_for(case_index, game_config)


@pytest.fixture
def api_player(qa, qa_config, game_config, qa_pair):
    """每个用例一条独立的角色会话。

    曾经改成整轮复用（会话池），实测**没有**降低抖动率，却因为少了"重新登录会从数据库重载角色"
    这一层意外的状态重置，暴露出两个真实的状态泄漏（宠物羊、HP/atk_xp）。所以退回复用，
    等把宠物/运行期状态的回收补齐之后再考虑。
    """
    observer_name, target_name = qa_pair
    game_config = {**game_config, "observer": observer_name, "target": target_name}
    command = [os.path.expandvars(part) for part in game_config["bridge_command"]]
    log = resolve_path(qa_config, game_config["server_log"]) if game_config.get("server_log") else None
    connection = Bridge(command, cwd=resolve_path(qa_config, game_config.get("bridge_cwd", ".")),
                        timeout=game_config.get("timeout", 20), server_log=log,
                        keepalive_op="get_chat_messages")
    try:
        yield Stendhal(connection, game_config, qa, observer=False)
    finally:
        connection.close()
        if getattr(connection, "stalls", None):
            qa.data["diagnostics"]["stall_dumps"] = connection.stalls
        qa.data["diagnostics"]["player_interface_messages"] = redact(connection.messages)
        qa.data["diagnostics"]["player_bridge_stderr"] = connection.stderr


@pytest.fixture
def observer(bridge, game_config, qa, request, qa_pair):
    if request.node._qa_meta["kind"] == "api":
        request.getfixturevalue("api_player")
    else:
        request.getfixturevalue("stendhal_ui")
    observer_name, target_name = qa_pair
    if request.node._qa_meta["kind"] == "api":
        return Stendhal(bridge, {**game_config, "observer": observer_name, "target": target_name}, qa)
    # UI 用例的目标是模拟器里那个角色，只轮换观察者账号
    return Stendhal(bridge, {**game_config, "observer": observer_name}, qa)


@pytest.fixture
def stendhal_ui(android, game_config):
    ui = StendhalUI(android, game_config)
    try:
        ui.ensure_login()
        yield ui
    finally:
        try:
            ui.record_timing()          # 成功失败都留一份 UI 耗时，便于分析成本
        except Exception:
            pass
        ui.close()


@pytest.fixture
def prepare(observer, qa, request):
    snapshots = []
    def ensure_target_online(api_player):
        """登录自校验握手：确认目标在线，也就是确认"我这条登录才是当前会话"。

        为什么需要：服务端对**同一账号**的重复登录会静默踢掉前一个会话。若上一条用例的角色会话
        断开被处理得比本次登录更晚，服务端会把**新**会话当成旧的移除——现象就是用例突然报
        Target character is not online，而服务端日志里什么都没有（实测复现过两次）。
        校验用 inspect：它读的是目标实时状态，一定过服务端。不在线就重登并退避重试。
        """
        for attempt in range(4):
            try:
                observer._guarded("inspect", read_only=True)
                return True
            except Exception as error:
                if "is not online" not in str(error):
                    raise
                observer.evidence.data.setdefault("diagnostics", {}).setdefault(
                    "login_handshake", []).append(f"第 {attempt + 1} 次: {str(error)[:100]}")
                api_player._reconnect(f"login handshake {attempt + 1}: target offline")
                time.sleep(1.5 * (attempt + 1))
        return False

    def start(**fields):
        """准备一段状态；可以在同一条用例里调用多次（分段准备，例如先在一个 NPC 那买、再到另一个区域卖）。

        每开新的一段前先还原上一段——两个原因：QaProbe 对同一角色只允许一个 active 快照；
        而且新一段应该在"用例开始时的那份状态"上准备，不是叠在上一段的结果上。
        各段的效果不跨段保留：需要延续就在后一段的前置里显式写出来（例如把上一段的实测结果
        写进后一段的 money/items），这样每段的期望仍然来自设计条目而不是环境残留。
        """
        if not snapshots and request.node._qa_meta["kind"] == "api":
            ensure_target_online(request.getfixturevalue("api_player"))
        if snapshots:
            observer.restore(snapshots[-1])
            snapshots.pop()
        try:
            result = observer.prepare(**fields)
        except Exception as error:
            api_player = (request.getfixturevalue("api_player") if request.node._qa_meta["kind"] == "api" else None)
            if api_player is None:
                raise
            if "is not online" in str(error):
                # 检查时还在线、准备时已经掉线：把角色重新拉上线再准备一次
                observer.evidence.data["diagnostics"].setdefault("online_recovery", []).append(str(error)[:200])
                api_player._reconnect("target dropped before prepare")
            elif "Fixture item exists outside bag" in str(error):
                # 上一个用例失败时把装备留在了身上（右手短剑/未收回背包的 buckler）：
                # 按出厂状态回收装备与背包后再准备一次，否则后续用例会连环失败
                from gameqa.recovery import reset_character
                observer.evidence.data["diagnostics"].setdefault("gear_recovery", []).append(
                    {"error": str(error)[:200], "reset": reset_character(api_player, observer)})
            else:
                raise
            result = observer.prepare(**fields)
            # 自愈成功后清掉上面可能落下的假标记：用例其实没问题
            if observer.evidence.data.get("failure_kind") == "preparation_error":
                observer.evidence.data.pop("failure_kind")
        snapshots.append(result["snapshot_id"])
        return result["after"]
    try:
        yield start
    finally:
        if snapshots:
            try:
                if request.node._qa_meta['kind'] == 'ui':
                    ui = request.getfixturevalue('stendhal_ui')
                    if not ui.entered:
                        ui.ensure_login()
                observer.restore(snapshots[-1])
            except Exception as error:
                # 保留原快照供恢复；清空快照或重置角色会丢掉用例前的状态。
                observer.evidence.data["diagnostics"].setdefault("restore_failures", []).append(str(error)[:300])
                observer.evidence.data["diagnostics"]["pending_snapshots"] = list(snapshots)
                raise
