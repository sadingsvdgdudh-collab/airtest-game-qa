"""共用运行锁：面板、命令行与清理脚本靠它互相让路（flock，跨进程）。"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from gameqa.run_lock import RunBusy, RunLock, run_active     # noqa: E402


def test_lock_marks_project_as_busy_and_releases_on_close(tmp_path):
    assert run_active(tmp_path) is False
    lock = RunLock.acquire(tmp_path)
    try:
        assert run_active(tmp_path) is True
    finally:
        lock.close()
    assert run_active(tmp_path) is False


def test_second_holder_is_refused_while_lock_is_held(tmp_path):
    first = RunLock.acquire(tmp_path)
    try:
        with pytest.raises(RunBusy):
            RunLock.acquire(tmp_path)
    finally:
        first.close()
    second = RunLock.acquire(tmp_path)          # 放开后可以再拿
    second.close()


def test_context_manager_releases_the_lock(tmp_path):
    with RunLock.acquire(tmp_path):
        assert run_active(tmp_path) is True
    assert run_active(tmp_path) is False


def test_lock_is_per_project(tmp_path):
    other = tmp_path / "another"
    other.mkdir()
    lock = RunLock.acquire(tmp_path)
    try:
        assert run_active(tmp_path) is True
        assert run_active(other) is False       # 另一个项目不受影响
    finally:
        lock.close()
