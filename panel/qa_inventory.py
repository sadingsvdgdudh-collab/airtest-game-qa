"""面板自带的 pytest 插件：把框架里已实现的用例清单（game/module/kind/id）以 JSON 打出来。

只做收集，不执行任何用例；框架代码不需要任何改动。
用法：pytest cases --collect-only -q -p gameqa.pytest_plugin -p qa_inventory ...
"""
import collections
import json


def pytest_collection_modifyitems(config, items):
    inventory = collections.defaultdict(lambda: collections.defaultdict(lambda: collections.defaultdict(list)))
    titles = {}
    for item in items:
        marker = item.get_closest_marker("case")
        if not marker:
            continue
        meta = marker.kwargs
        inventory[meta["game"]][meta["module"]][meta["kind"]].append(meta["id"])
        if meta.get("title"):
            titles[meta["id"]] = meta["title"]
    print("INVENTORY " + json.dumps(inventory, ensure_ascii=False))
    # 中文名单列一行：INVENTORY 的结构被面板多处按 {game:{module:{kind:[id]}}} 使用，不塞进去。
    print("TITLES " + json.dumps(titles, ensure_ascii=False))
    raise SystemExit(0)
