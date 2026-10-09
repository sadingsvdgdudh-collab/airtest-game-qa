"""账号池：命名、轮换与向后兼容（pool_size 缺省 = 只用原有一个账号）。"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from gameqa.accounts import observer_pool, pair_for, pool_size, target_pool     # noqa: E402

GAME = {"api_target": "qaplayera", "observer": "qaobserver", "pool_size": 3}


def test_pool_names_follow_stendhal_reserved_naming():
    assert target_pool(GAME) == ["qaplayera", "qaplayerb", "qaplayerc"]
    assert observer_pool(GAME) == ["qaobserver", "qaobserverb", "qaobserverc"]


def test_rotation_keeps_adjacent_cases_on_different_accounts():
    pairs = [pair_for(index, GAME) for index in range(6)]
    assert len({observer for observer, _ in pairs[:3]}) == 3
    assert len({target for _, target in pairs[:3]}) == 3
    assert pairs[0] == ("qaobserver", "qaplayera")
    assert pairs[3] == pairs[0]        # 轮回收敛


def test_default_is_single_account_for_backwards_compatibility():
    game = {"api_target": "qaplayera", "observer": "qaobserver"}
    assert pool_size(game) == 1
    assert pair_for(5, game) == ("qaobserver", "qaplayera")


def test_broken_pool_size_falls_back_to_one():
    assert pool_size({"pool_size": "nonsense"}) == 1
