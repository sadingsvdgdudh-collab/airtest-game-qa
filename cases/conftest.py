import os
from pathlib import Path

import pytest

from gameqa.bridge import Bridge, redact
from gameqa.config import resolve_path
from gameqa.stendhal import Stendhal
from gameqa.stendhal_ui import StendhalUI


@pytest.fixture
def api_player(qa, qa_config, game_config):
    """每个用例一条独立的角色会话。

    曾经改成整轮复用（会话池），实测**没有**降低抖动率，却因为少了"重新登录会从数据库重载角色"
    这一层意外的状态重置，暴露出两个真实的状态泄漏（宠物羊、HP/atk_xp）。所以退回复用，
    等把宠物/运行期状态的回收补齐之后再考虑。
    """
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
def observer(bridge, game_config, qa, request):
    if request.node._qa_meta["kind"] == "api":
        request.getfixturevalue("api_player")
    else:
        request.getfixturevalue("stendhal_ui")
    return Stendhal(bridge, game_config, qa)


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
            observer.restore(snapshots.pop())
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
        # 用例失败时也做一次自动回收：残留（尤其是宠物——它不在快照里）会污染后面的用例。
        # 判定用已记录的步骤：qa.check 失败会留下一枚 outcome=failed 的步骤。
        if any(step.get("outcome") == "failed" for step in observer.evidence.data.get("steps", [])):
            try:
                from gameqa.recovery import reset_character
                player = request.getfixturevalue("api_player") if request.node._qa_meta["kind"] == "api" else None
                if player is not None:
                    observer.evidence.data.setdefault("diagnostics", {}).setdefault("auto_recovery", []).append(
                        reset_character(player, observer))
            except Exception as recovery_error:
                observer.evidence.data.setdefault("diagnostics", {}).setdefault("auto_recovery", []).append(
                    {"error": f"{type(recovery_error).__name__}: {recovery_error}"})
        if snapshots:
            if request.node._qa_meta['kind'] == 'ui':
                ui = request.getfixturevalue('stendhal_ui')
                if not ui.entered:
                    ui.ensure_login()
            try:
                observer.restore(snapshots[-1])
            except Exception as error:
                # 还原失败（用例中途出错、连接抖动、投影不一致…）：至少把自己留下的快照精确丢掉，
                # 否则这一个残留会挡住同一次运行里后面所有用例（实测过 20+ 条连环失败）。
                observer.evidence.data["diagnostics"].setdefault("restore_failures", []).append(str(error)[:300])
                for token in snapshots:
                    try:
                        observer.forget(token=token)
                    except Exception:
                        pass
                # 还原不成功 -> 用例改过的装备/背包会留在角色身上，污染后续用例。
                # 这里按 api 用例自动回收（UI 角色的会话在模拟器里，不去抢）。
                if request.node._qa_meta["kind"] == "api":
                    try:
                        from gameqa.recovery import reset_character
                        player = request.getfixturevalue("api_player")
                        observer.evidence.data["diagnostics"].setdefault("auto_recovery", []).append(
                            reset_character(player, observer))
                    except Exception as recovery_error:
                        observer.evidence.data["diagnostics"].setdefault("auto_recovery", []).append(
                            {"error": f"{type(recovery_error).__name__}: {recovery_error}"})
                raise
