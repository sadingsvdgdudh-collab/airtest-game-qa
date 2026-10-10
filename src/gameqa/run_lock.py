"""角色会话共用一把本机文件锁；子进程只能通过显式传入的 fd 继承。"""
import fcntl
import os
from pathlib import Path


class RunBusy(RuntimeError):
    pass


class RunLock:
    @classmethod
    def acquire(cls, project, inherited_fd=None):
        path = Path(project).resolve() / ".gameqa-run.lock"
        fd = (os.open(path, os.O_RDWR | os.O_CREAT, 0o600) if inherited_fd is None
              else os.dup(inherited_fd))
        try:
            if inherited_fd is not None:
                actual, expected = os.fstat(fd), path.stat()
                if (actual.st_dev, actual.st_ino) != (expected.st_dev, expected.st_ino):
                    raise ValueError("传入的运行锁 fd 不属于当前项目")
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as error:
                raise RunBusy("已有测试、角色清理或健康检查在进行，请等待结束后再试。") from error
        except BaseException:
            os.close(fd)
            raise
        if inherited_fd is not None:
            os.close(inherited_fd)
        lock = cls()
        lock.fd = fd
        return lock

    def fileno(self):
        return self.fd

    def close(self):
        if self.fd is not None:
            # 不调用 LOCK_UN：继承 fd 的子进程结束不能提前解除父进程的锁。
            os.close(self.fd)
            self.fd = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def run_active(project):
    try:
        with RunLock.acquire(project):
            return False
    except RunBusy:
        return True
