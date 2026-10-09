"""清理测试角色的**可清理残留**：停攻击、清寻路、清持续状态；并报告背包里的持久道具。

为什么需要这个脚本
------------------
R1 快照的恢复只在用例**正常退出**时执行（`cases/conftest.py` 的 fixture finally）。
中途 kill 掉一次运行，恢复就不会跑，而 Stendhal 会把角色状态定期存盘——
于是"跑一半留下的状态"被固化进角色。实测过两种残留：

* `statuses` / 攻击目标非空 → UI 用例的前置守卫直接拒绝运行（"needs no active status or combat"）；
* 背包里多出一个 `money` 道具 → "背包内容精确相等"的断言每轮必挂。

**能清什么（实测）**：本脚本做一次 `prepare()` + `restore()` 往返。`prepare` 内部会
`stopAttack()/clearPath()/stop()`，而 `restore` 恢复的投影**不含 statuses 与攻击目标**
（见 QaProbe 的 `projection()`），所以攻击/寻路/持续状态被真正清掉，其余（背包、装备、
xp/hp/level、任务、位置、计数）原样还原。

**默认不动背包**：只清状态，背包里的持久道具只报告。原因是探针只支持"快照式"准备——
`prepare` 必留一个 active 快照、必须 `restore` 才能解除，而 `restore` 会把刚清掉的道具还原回来。

**要清背包就加 `--clear-items`**：它会 `prepare(items={每个背包道具: 0}, money=0)`（restore 会把道具还回来，
所以不能 restore），随后调探针的 `forget` 丢掉那个快照——效果留在服务端，**不需要重启主服**。
实测：`qaplayera` 背包里残留的 1 个 beer 就是这样清掉的（它曾让 `ST-SHOP-API-006-merge` 报
`Bag is full for money`、`-no-space` 的前置守卫失败）。

用法
----
    python scripts/cleanup_characters.py              # 清 target / api_target 的状态残留
    python scripts/cleanup_characters.py --dry-run    # 只看现状，不改动
    python scripts/cleanup_characters.py --only qaplayer

注意：会话与快照层的残留（`bridge is closed`、`An active snapshot already exists`）
不在本脚本范围内——那需要重启主服（面板的「停止/启动主服」）。
"""

import argparse
import copy
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gameqa.bridge import Bridge                                    # noqa: E402
from gameqa.config import load_config, resolve_path                 # noqa: E402
from gameqa.evidence import Evidence                                # noqa: E402
from gameqa.recovery import clear_bag, normalize_weapon             # noqa: E402
from gameqa.stendhal import Stendhal                                 # noqa: E402


def characters(game):
    """要清理的角色：会打游戏、会攒道具的那两个。

    不含 `observer`：QaProbe 要求"读取方必须是另一个角色"，所以观察者角色读不到、
    也 prepare 不了自己（实测 `Probe must use a separate observer character`）。
    它只负责读，不会攒道具，跳过即可（`--only qaobserver` 会如实报错）。
    """
    names = [game.get("target"), game.get("api_target")]
    return [name for index, name in enumerate(names) if name and name not in names[:index]]


def connect(qa_config, game, name, observer):
    """开一条桥：observer=True 时以 `observer` 账号登录、读 `name`；否则以 `name` 本人登录。

    框架有硬性约束"目标角色的状态必须由独立观察者读"（`stendhal.inspect` 里的守卫），
    所以读状态与改状态要分两条连接——和用例里 api_player + observer 的分工一致。
    """
    scoped = copy.deepcopy(game)
    scoped["target"] = name
    command = [os.path.expandvars(part) for part in scoped["bridge_command"]]
    bridge = Bridge(command, cwd=resolve_path(qa_config, scoped.get("bridge_cwd", ".")),
                    timeout=scoped.get("timeout", 20))
    qa = Evidence(f"cleanup-{name}", "/tmp/qa-cleanup", {})
    return bridge, Stendhal(bridge, scoped, qa, observer=observer)


def report(result):
    before = result["before"]
    print(f"\n[{result['name']}] 包里：{before['bag'] or '空'} | 右手：{before['rhand'] or '空'}"
          f" | hp/xp/level：{before['hp']}/{before['xp']}/{before['level']}"
          f" | statuses：{before['statuses'] or '无'} | 攻击目标：{before['target']}")
    if result.get("after"):
        after = result["after"]
        print(f"  清理后：包里 {after['bag'] or '空'} | hp/xp/level：{after['hp']}/{after['xp']}/{after['level']}"
              f" | statuses：{after['statuses'] or '无'} | 攻击目标：{after['target']}")


def flatten(state):
    """把投影压成面板好读的一行：背包内容、持续状态、攻击目标，以及"是否脏"。"""
    bag = [(name, qty) for name, qty in state["bag"]]
    return {"bag": bag, "statuses": state["statuses"] or [], "target": state["target"],
            "hp": state["hp"], "level": state["level"],
            "dirty": bool(bag) or bool(state["statuses"]) or bool(state["target"])}


def project(state):
    """把一次 inspect/prepare 的投影收成报告用的形状。"""
    attrs = state["attributes"]
    return {"bag": [(item["name"], int(item.get("quantity", 1))) for item in state["slots"]["bag"]],
            "rhand": [item["name"] for item in state["slots"]["rhand"]],
            "hp": attrs.get("hp"), "xp": attrs.get("xp"), "level": attrs.get("level"),
            "statuses": state.get("statuses"), "target": attrs.get("target")}


def _ancestors():
    """自己与所有祖先进程的 pid；pgrep -f 会把"命令行里提到这句话"的调用方自己也算进来。"""
    pids, pid = set(), os.getpid()
    while pid and pid not in pids:
        pids.add(pid)
        try:
            out = subprocess.run(["ps", "-o", "ppid=", "-p", str(pid)], capture_output=True, text=True).stdout.strip()
            pid = int(out) if out.isdigit() else 0
        except Exception:
            break
    return pids


def game_run_active():
    """有测试在跑时不许清理：清理会丢弃快照、清空背包，会打乱正在跑的用例。"""
    ignore = _ancestors()
    for pattern in ("-m gameqa run", "pytest cases"):
        done = subprocess.run(["pgrep", "-f", pattern], capture_output=True, text=True)
        for pid in done.stdout.split():
            if pid.isdigit() and int(pid) not in ignore:
                return True
    return False


def clean(name, qa_config, game, dry_run, clear_items=False, normalize_gear=False, factory_weapon="club"):
    """清一个角色的状态残留（prepare + restore 往返），并报告背包里的持久道具。

    两步缺一不可：
    1. 以**角色本人**登录把它拉上线——观察者读不到离线角色，而测试角色平时是离线的；
    2. 用**独立观察者**连接 `prepare()` 再 `restore()`——QaProbe 要求每个操作都由 `qaobserver`
       发起（"Probe must use a separate observer character"），且同一个目标同时只允许一个 active 快照，
       所以必须成对调用，不能只 prepare。
    """
    actor_bridge, actor = connect(qa_config, game, name, observer=False)
    try:
        obs_bridge, observer = connect(qa_config, game, name, observer=True)
        try:
            result = {"name": name, "online": True, "before": project(observer.inspect())}
            result.update(flatten(result["before"]))
            if dry_run:
                return result
            # 这是**人工**工具：被它清的角色很可能刚被一次杀掉的运行留下快照，而那个快照很新，
            # 框架的自愈（只丢 60 秒以上的）不会动它。这里显式丢弃该角色的全部快照；
            # 上面的 game_run_active() 已经挡掉了"正在跑测试"的情况。
            result["forgotten"] = observer.forget(older_than_seconds=0)["forgotten"]
            if clear_items:
                # 清背包的效果不能靠 restore（restore 会把道具还回来），所以准备完直接丢掉快照：
                # 状态留在服务端，快照用 forget 撤掉，不需要重启主服。
                # 道具名必须放进 items 里：QaProbe 只允许白名单里的顶层字段（money/items/quests/…），
                # 把道具名当顶层字段传会被拒："Unsupported fixture field: beer"。
                cleared = clear_bag(observer)
                result["cleared"] = cleared["cleared"] + ["money", "攻击", "寻路", "持续状态"]
                result["after"] = project(observer.inspect())
                result["needs_server_restart"] = True
                result.update(flatten(result["after"]))
                return result
            if normalize_gear:
                # 装备漂移的回收：用例被连接中断打断时走不到快照还原，右手会留着别的东西
                # （实测：出厂是 club，被留成 short sword，导致 3 条假设木棍的用例必挂）。
                # 用真实 equip 动作换回来：现右手 → 背包，再把背包里的出厂武器装上右手。
                result["gear"] = normalize_weapon(actor, observer, factory_weapon)
                # flatten() 吃的是 project() 的形状（顶层有 bag），inspect() 的槽位在 slots 里
                result["after"] = project(observer.inspect())
                result.update(flatten(result["after"]))
                return result
            token = observer.prepare()["snapshot_id"]     # 不带字段：只触发 stop/clearPath/stop
            observer.restore(token)                       # 还原投影（不含 statuses/攻击目标）
            result["after"] = project(observer.inspect())
            result["cleared"] = ["攻击", "寻路", "持续状态"]
            result.update(flatten(result["after"]))   # 顶层给面板读的摘要；after 保留完整投影（含 xp）
            return result
        except Exception as error:
            return {"name": name, "online": False, "error": f"{type(error).__name__}: {error}"}
        finally:
            obs_bridge.close()
    finally:
        actor_bridge.close()                          # 登出，让服务端把状态存下来


def main():
    parser = argparse.ArgumentParser(description="清理测试角色背包里的持久残留")
    parser.add_argument("--dry-run", action="store_true", help="只报告现状")
    parser.add_argument("--only", action="append", help="只清指定角色（可重复）")
    parser.add_argument("--game", default="stendhal", help="配置里的游戏段名，默认 stendhal")
    parser.add_argument("--json", action="store_true", help="给面板等消费者读的结果（一行 JSON）")
    parser.add_argument("--normalize-gear", action="store_true",
                        help="把右手换成出厂武器（默认 club）：装备漂移的回收，用真实 equip 动作")
    parser.add_argument("--clear-items", action="store_true",
                        help="连背包道具一起清（prepare 清空后 forget 撤掉快照，不需要重启主服）")
    args = parser.parse_args()

    qa_config = load_config(os.environ["GAMEQA_CONFIG"])
    game = qa_config["games"][args.game]
    if game_run_active():
        print("检测到正在运行的测试（gameqa run / pytest cases）；清理会打断它，已拒绝。", file=sys.stderr)
        return 2
    wanted = args.only or characters(game)
    if args.json:
        results = [clean(name, qa_config, game, args.dry_run, args.clear_items, args.normalize_gear)
                   for name in wanted]
        print(json.dumps({"characters": results, "dry_run": args.dry_run}, ensure_ascii=False))
        return 1 if any(not r["online"] for r in results) else 0
    print(f"角色：{', '.join(wanted)}" + ("（dry-run，不改动）" if args.dry_run else ""))
    failures = 0
    for name in wanted:
        result = clean(name, qa_config, game, args.dry_run, args.clear_items, args.normalize_gear)
        if not result["online"]:
            failures += 1
            print(f"\n[{name}] 连不上：{result['error']}")
            continue
        report(result)
        if args.dry_run:
            continue
        if "error" in result:
            failures += 1
            print(f"  清理失败：{result['error']}")
            continue
        after = result.get("after") or result["before"]
        bag = after["bag"]
        forgotten = result.get("forgotten") or []
        if forgotten:
            print("  先丢弃了 " + str(len(forgotten)) + " 个残留快照：" + "、".join(f["snapshot_id"][:8] for f in forgotten))
        gear = result.get("gear")
        if gear:
            print("  装备回收：" + ("；".join(gear["steps"]) or "无需调整") + f" → 右手 {gear['rhand']}")
        print("  已清：" + ("、".join(result.get("cleared") or []) if args.clear_items else "攻击目标 / 寻路 / 持续状态"))
        print(f"  背包里的持久道具（本脚本只报告、不清）：{bag or '无'}")
    print("\n完成" + (f"，{failures} 个角色连不上" if failures else ""))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
