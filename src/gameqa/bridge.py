"""JSONL subprocess boundary, shared by independent game protocols."""
import json
import os
import queue
from pathlib import Path
import shutil
import subprocess
import threading
import time


SENSITIVE = {"password", "passwd", "token", "secret", "authorization"}


def redact(value):
    if not isinstance(value, (dict, list, tuple, str)):
        return value
    secrets = [secret for name, secret in os.environ.items()
               if name.startswith("GAMEQA_") and any(word in name for word in ("PASSWORD", "TOKEN", "SECRET"))
               and len(secret) >= 4]

    def clean(item):
        if isinstance(item, dict):
            return {key: "[redacted]" if key.lower() in SENSITIVE else clean(child)
                    for key, child in item.items()}
        if isinstance(item, (list, tuple)):
            return [clean(child) for child in item]
        if isinstance(item, str):
            for secret in secrets:
                item = item.replace(secret, "[redacted]")
        return item

    return clean(value)


# 基础设施抖动的签名：这些不是用例判定的业务事实。
# 运行器据此决定"可以重跑一次"，封装层据此决定"不要把准备失败记成用例的错"。
INFRA_SIGNATURES = ("is not online", "Game connection closed", "TimeoutException",
                    "SocketException", "EOFException", "bridge exited", "no confirmed response")


def is_infrastructure_error(error):
    text = str(error)
    return any(signature in text for signature in INFRA_SIGNATURES)


class TransientError(RuntimeError):
    """An observation or connection can be tried again without a business action."""


class IndeterminateAction(RuntimeError):
    """An action may have committed. Inspect state before doing anything again."""


def server_pid(server_log):
    """从 server_log 推出服务端 pid：同目录下的 server.pid。"""
    if not server_log:
        return None
    base = Path(server_log).parent
    for candidate in (base / "server.pid", base.parent / "server.pid"):
        try:
            return int(candidate.read_text().strip())
        except Exception:
            continue
    return None


def jstack_binary():
    """找可用的 jstack：优先服务端那个 JDK（版本也要匹配），并排除 macO 自带的占位符。

    /usr/bin/jstack 在没有装 Java 的机器上是个存根，只会打印 "Unable to locate a Java Runtime"，
    所以候选要按顺序探测，PATH 放最后。
    """
    candidates = []
    java = os.environ.get("STENDHAL_JAVA")
    if java:
        candidates.append(Path(java).parent / "jstack")
    work = os.environ.get("GAMEQA_WORK_DIR")
    if work:
        candidates.extend(sorted(Path(work).glob("tools/*/bin/jstack")))
    found = shutil.which("jstack")
    if found:
        candidates.append(Path(found))
    for candidate in candidates:
        try:
            if not candidate.exists():
                continue
            probe = subprocess.run([str(candidate), "-h"], capture_output=True, text=True, timeout=15)
            if "Unable to locate a Java Runtime" in (probe.stdout + probe.stderr):
                continue
            return str(candidate)
        except Exception:
            continue
    return None


class BridgeError(RuntimeError):
    pass


class Bridge:
    # ponytail: one sequential caller; multiplex only if concurrent cases are required.
    def __init__(self, command, cwd=None, timeout=15, min_interval=0.18, server_log=None,
                 keepalive_op=None, keepalive_args=None, keepalive_interval=5.0):
        if not command or not isinstance(command, list):
            raise ValueError("bridge command must be a nonempty argument list")
        self.command, self.cwd = command, cwd
        self.timeout = timeout
        self.min_interval = min_interval        # 秒；0.18 -> 每通道最多约 5.5 条消息/秒
        self.last_request = 0.0
        # 停顿看门狗：请求超过阈值就 dump 服务端 jstack，用来定位服务端僵住时卡在哪一帧
        self.server_log = server_log
        self.stall_threshold = 1.5
        self.stalls = []
        self._last_stall_dump = 0.0
        # 保活：实测服务端对静默约 10-15 秒的连接会直接关掉（199 次采样全是服务端先发 FIN）。
        # 桥只在框架要操作时才说话，所以长等待（UI 走路、长 await、用例间空隙）会被关。
        self.keepalive_op = keepalive_op
        self.keepalive_args = keepalive_args or {}
        self.keepalive_interval = keepalive_interval
        self._lock = threading.RLock()
        self.keepalive_sent = 0
        self.keepalive_errors = []
        self.messages = []
        self.stderr = []
        self.counter = 0
        self._start()

    def _start(self):
        self.process = subprocess.Popen(self.command, cwd=self.cwd, stdin=subprocess.PIPE,
                                        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                        text=True, encoding="utf-8", bufsize=1)
        self.incoming = queue.Queue()
        self.closed = False
        self._keepalive_stop = threading.Event()
        self._keepalive_thread = None
        threading.Thread(target=self._read_stdout, args=(self.process.stdout, self.incoming), daemon=True).start()
        threading.Thread(target=self._read_stderr, args=(self.process.stderr,), daemon=True).start()

    def _read_stdout(self, stream, incoming):
        for line in stream:
            incoming.put(line)
        incoming.put(None)

    def _read_stderr(self, stream):
        for line in stream:
            # Store bounded diagnostics; the bridge must never print credentials.
            self.stderr.append(line.rstrip())
            if len(self.stderr) > 1000:
                del self.stderr[:100]

    def reopen(self):
        with self._lock:
            if not self.closed:
                raise BridgeError("close the old session before opening a new one")
            self.messages.append({"direction": "lifecycle", "event": "reopen", "time": time.time()})
            self._start()

    def call(self, op, args=None, *, read_only=False, timeout=None):
        with self._lock:
            result = self._call(op, args, read_only=read_only, timeout=timeout)
            if op == "login":
                self._start_keepalive()
        return result

    def _call(self, op, args=None, *, read_only=False, timeout=None):
        if self.closed:
            raise BridgeError("bridge is closed")
        self._throttle()
        started = time.monotonic()
        self.counter += 1
        request = {"id": self.counter, "op": op, "args": args or {}}
        self.messages.append({"direction": "request", "time": time.time(), **redact(request)})
        try:
            self.process.stdin.write(json.dumps(request, ensure_ascii=False) + "\n")
            self.process.stdin.flush()
            deadline = time.monotonic() + (timeout or self.timeout)
            while True:
                line = self.incoming.get(timeout=max(0.001, deadline - time.monotonic()))
                if line is None:
                    raise BrokenPipeError("bridge exited")
                try:
                    response = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise BridgeError("non-JSON output on bridge stdout") from exc
                self.messages.append({"direction": "response", "time": time.time(), **redact(response)})
                if response.get("id") != request["id"]:
                    raise BridgeError(f"response id mismatch: {response.get('id')}")
                if response.get("ok") is not True:
                    error = response.get("error", {})
                    # IOException 里最常见的是原服那句 "Game connection closed"（服务端把连接关了）：
                    # 和超时一样属于"没有确认响应"，交给上层的重连+重试处理，而不是当作业务失败。
                    if error.get("type") in {"TimeoutException", "SocketException", "EOFException", "IOException"}:
                        self.close()
                        kind = TransientError if read_only else IndeterminateAction
                        raise kind(f"{op}: {error.get('type')}; action was not resent")
                    raise BridgeError(f"{error.get('type', 'BridgeError')}: {error.get('message', error)}")
                elapsed = time.monotonic() - started
                if elapsed > self.stall_threshold:
                    self._dump_stall(op, elapsed, timed_out=False)
                return response.get("result")
        except (queue.Empty, BrokenPipeError, OSError) as exc:
            self._dump_stall(op, time.monotonic() - started, timed_out=True)
            self.close()
            error = TransientError if read_only else IndeterminateAction
            raise error(f"{op}: no confirmed response; request was not resent") from exc

    def _start_keepalive(self):
        """登录成功后启动保活线程（幂等）。"""
        if self.closed or not self.keepalive_op or self._keepalive_thread is not None:
            return
        stop = self._keepalive_stop
        def beat():
            while not stop.wait(1.0):
                try:
                    with self._lock:
                        # 旧线程可能正在等锁；重开后也不能操作新会话。
                        if stop.is_set() or self.closed:
                            return
                        if time.monotonic() - self.last_request < self.keepalive_interval:
                            continue
                        self._call(self.keepalive_op, dict(self.keepalive_args), read_only=True)
                        self.keepalive_sent += 1
                except Exception as error:
                    self.keepalive_errors.append(f"{type(error).__name__}: {str(error)[:80]}")
        self._keepalive_thread = threading.Thread(target=beat, name="qa-keepalive", daemon=True)
        self._keepalive_thread.start()

    def _dump_stall(self, op, elapsed, *, timed_out):
        """请求超过阈值（或超时）时 dump 一次服务端线程栈。

        剩下的抖动是服务端间歇僵住十几秒；只看客户端日志无法知道卡在哪一帧，
        jstack 会指出世界线程当刻停在哪个方法（H2 写、区域存档……）。限频 5 秒、整轮最多 40 份。
        """
        now = time.monotonic()
        if now - self._last_stall_dump < 5 or len(self.stalls) >= 40:
            return
        self._last_stall_dump = now
        pid, binary = server_pid(self.server_log), jstack_binary()
        if not pid or not binary:
            self.stalls.append({"op": op, "seconds": round(elapsed, 2), "timed_out": timed_out,
                                "dump": None, "why": f"pid={pid} jstack={binary}"})
            return
        base = Path(self.server_log).parent.parent if self.server_log else Path(self.cwd or ".")
        directory = base / "qa-stalls"
        directory.mkdir(exist_ok=True)
        path = directory / f"{time.strftime('%Y%m%dT%H%M%S')}-{op}{'-timeout' if timed_out else ''}.txt"
        try:
            result = subprocess.run([binary, str(pid)], capture_output=True, text=True, timeout=30)
            body = result.stdout or result.stderr
        except Exception as error:
            body = f"jstack failed: {type(error).__name__}: {error}"
        path.write_text(f"# op={op} elapsed={elapsed:.2f}s timed_out={timed_out} pid={pid}\n" + body,
                        encoding="utf-8")
        self.stalls.append({"op": op, "seconds": round(elapsed, 2), "timed_out": timed_out,
                            "dump": str(path)})

    def _throttle(self):
        """按最小间隔限速。

        原服的洪泛保护实测在**每通道约 12 条消息/秒**就断开连接：
        Disconnecting Channel ... for flooding server: [ time: 1 send bytes: 2137 send messages: 12 ]。
        框架的等待类原语（await_state 等）是无间隔轮询，一次断连后重试又会立刻再次洪泛，
        于是表现为"用例随机报错、重试仍然失败"。这里给每个连接定一个远低于阈值的上限。
        """
        wait = self.min_interval - (time.monotonic() - self.last_request)
        if wait > 0:
            time.sleep(wait)
        self.last_request = time.monotonic()

    def close(self):
        with self._lock:
            self._keepalive_stop.set()
            # _call 也会持锁关闭；join 会等待自己或等待同一把锁。
            self._keepalive_thread = None
            # 关进程绝不能抛：进程被杀（瞬断或人工注入）时管道已经断了，收尾里的异常会把
            # 一条本来已经通过的用例标成失败（实测踩到过 BrokenPipeError）。看门狗只关心状态。
            if self.closed:
                return
            self.closed = True
            try:
                if self.process.poll() is None:
                    self.process.terminate()
                    try:
                        self.process.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        self.process.kill()
                        self.process.wait(timeout=3)
            except Exception:
                pass
            for stream in (self.process.stdin, self.process.stdout, self.process.stderr):
                try:
                    if stream:
                        stream.close()
                except Exception:
                    pass

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
