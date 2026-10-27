"""失败归类：业务 / 环境 / 框架 必须能分开，否则报告会把环境噪音算成缺陷。"""
from gameqa.evidence import classify_failure


def case(outcome, phases=None, steps=None, diagnostics=None):
    return {"outcome": outcome, "phases": phases or {}, "steps": steps or [],
            "diagnostics": diagnostics or {}}


def test_business_failure_is_an_assertion():
    data = case("failed", {"setup": "passed", "call": "failed"},
                [{"title": "第八步保留八枚棋子", "outcome": "failed", "expected": 8, "actual": 0}])
    assert classify_failure(data) == "business"


def test_environment_failure_matches_infra_signature():
    data = case("error", {"setup": "failed",
                          "setup_detail": "BridgeError: Shardy handshake did not complete in 5 seconds"})
    assert classify_failure(data) == "environment"


def test_harness_failure_is_neither():
    data = case("error", {"setup": "failed", "setup_detail": "TypeError: fixture 少传一个参数"})
    assert classify_failure(data) == "harness"


def test_business_failure_that_quotes_infra_text_stays_business():
    """断言失败但消息里恰好引用了 'Game connection closed'：以 outcome 为准，不许被签名抢走。"""
    data = case("failed", {"call": "failed",
                           "call_detail": "AssertionError: 断线提示应为 'Game connection closed'"})
    assert classify_failure(data) == "business"


def test_passed_and_skipped():
    assert classify_failure(case("passed", {"call": "passed"})) == "none"
    assert classify_failure(case("skipped", {"call": "skipped"})) == "skipped"
