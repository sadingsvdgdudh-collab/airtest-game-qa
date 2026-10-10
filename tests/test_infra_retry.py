"""基础设施重试的判定：只认抖动签名、只碰 error，断言失败与真 bug 都不重试。"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from gameqa.__main__ import infra_failed, summarize     # noqa: E402


def case(case_id, outcome, detail=""):
    return {"id": case_id, "outcome": outcome, "phases": {"call_detail": detail}}


def test_only_infrastructure_errors_are_retried():
    report = {"cases": [
        case("INFRA-ONLINE", "error", "IllegalStateException: Target character is not online: qaplayera"),
        case("INFRA-CLOSED", "error", "IOException: Game connection closed"),
        case("BUSINESS-FAIL", "failed", "AssertionError: expected 2, actual 3"),
        case("REAL-BUG", "error", "KeyError: 'bag'"),
        # 抖动落在用例体内时会被记成 failed：只要文本带抖动签名，仍然应该重试
        case("INFRA-IN-CALL", "failed", "IndeterminateAction: prepare: TimeoutException; action was not resent"),
    ]}
    assert infra_failed(report) == ["INFRA-ONLINE", "INFRA-CLOSED", "INFRA-IN-CALL"]


def test_retry_recovered_does_not_count_as_accepted():
    passed = {"id": "A", "outcome": "passed",
              "diagnostics": {"infra_retry": {"first_outcome": "error"}}}
    summary = summarize([{"cases": [passed]}])
    assert summary["all_passed"] is False          # 重试恢复不计完成验收
    assert summary["infra_retries"] == 1
    assert summary["unexplained_failures"] == []
    clean = summarize([{"cases": [{"id": "A", "outcome": "passed"}]}])
    assert clean["all_passed"] is True and clean["infra_retries"] == 0


def test_retry_metrics_separate_first_try_from_retried():
    """重试率口径：重试才过单独计数，绝不算进一次通过。"""
    def case(case_id, outcome, retried=False):
        return {"id": case_id, "outcome": outcome,
                "diagnostics": {"infra_retry": {"first_outcome": "error"}} if retried else {}}

    summary = summarize([{"cases": [case("A", "passed"), case("B", "passed", True),
                                    case("C", "passed", True), case("D", "failed")]}])
    assert summary["observations"] == 4
    assert summary["infra_retry_count"] == 2
    assert summary["infra_retry_rate"] == 0.5
    assert summary["first_try_passed"] == 1            # 只有 A 是一次通过
    assert summary["all_passed"] is False
    assert summary["unexplained_failures"] == ["D"]
    empty = summarize([{"cases": []}])
    assert empty["observations"] == 0 and empty["infra_retry_rate"] == 0.0
    assert empty["first_try_passed"] == 0


def test_retry_metrics_across_rounds_and_missing_flag():
    """多轮：按 case × round 计数；没有重试标记的旧报告也要算得出来。"""
    summary = summarize([{"cases": [{"id": "A", "outcome": "passed"}]},
                          {"cases": [{"id": "A", "outcome": "passed",
                                      "diagnostics": {"infra_retry": {"first_outcome": "error"}}}]}])
    assert summary["observations"] == 2
    assert summary["infra_retry_count"] == 1
    assert summary["first_try_passed"] == 1


def test_real_failures_are_reported_as_unexplained():
    summary = summarize([{"cases": [case("X", "failed", "AssertionError: nope")]}])
    assert summary["unexplained_failures"] == ["X"] and summary["all_passed"] is False


class FakeEvidence:
    def __init__(self):
        self.data = {"diagnostics": {}}

    def observe(self, title, function, retries=0):
        return function()


def test_shared_signature_list_is_the_only_definition():
    import gameqa.__main__ as runner
    from gameqa import bridge

    assert runner.INFRA_SIGNATURES is bridge.INFRA_SIGNATURES


def test_unconfirmed_prepare_is_reported_as_preparation_error():
    """prepare 不再重放；准备未确认就中止，应报告环境错误而不是业务失败。"""
    from gameqa.bridge import TransientError
    from gameqa.stendhal import Stendhal

    class Bridge:
        def __init__(self, error):
            self.error, self.calls, self.closed = error, 0, False

        def call(self, op, args=None, read_only=False):
            self.calls += 1
            if op == "forget":
                return {"forgotten": []}
            raise self.error

        def close(self):
            self.closed = True

        def reopen(self):
            self.closed = False

    def client(error):
        config = {"target": "qaplayera", "observer": "qaobserver", "host": "127.0.0.1", "port": 1,
                  "observer_password_env": "X", "player_password_env": "X"}
        os.environ["X"] = "secret"
        stendhal = Stendhal.__new__(Stendhal)
        stendhal.bridge, stendhal.config, stendhal.evidence = Bridge(error), config, FakeEvidence()
        stendhal.observer, stendhal.username, stendhal.password_env = True, "qaobserver", "X"
        return stendhal

    transient = client(TransientError("prepare: TimeoutException; action was not resent"))
    try:
        transient.prepare(money=0)
    except Exception:
        pass
    assert transient.evidence.data["failure_kind"] == "preparation_error"

    genuine = client(RuntimeError("Could not prepare location"))
    try:
        genuine.prepare(money=0)
    except Exception:
        pass
    assert genuine.evidence.data.get("failure_kind") == "preparation_error"
