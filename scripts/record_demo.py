#!/usr/bin/env python3
"""Record one real emulator UI case and preserve its independent report."""
import argparse
import os
from pathlib import Path
import select
import shutil
import subprocess
import sys
import time
import uuid


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", default="ST-SHOP-UI-001")
    parser.add_argument("--serial", default="emulator-5554")
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--report-dir", type=Path, required=True)
    parser.add_argument("--config")
    args = parser.parse_args()
    if args.video.exists() or args.report_dir.exists():
        parser.error("choose new video and report paths; existing evidence is never overwritten")
    adb = shutil.which("adb")
    if not adb and os.environ.get("ANDROID_HOME"):
        adb = str(Path(os.environ["ANDROID_HOME"]) / "platform-tools/adb")
    if not adb:
        parser.error("set ANDROID_HOME or add adb to PATH")
    prefix = [adb, "-s", args.serial]
    remote = f"/sdcard/gameqa-{uuid.uuid4().hex}.mp4"
    # Echo the PID of exactly this recorder; never kill unrelated device processes.
    script = f"screenrecord --size 720x1280 --bit-rate 2000000 --time-limit 180 {remote} & echo $!; wait"
    recording = subprocess.Popen(prefix + ["shell", script], stdout=subprocess.PIPE, text=True)
    pid = None
    try:
        if not select.select([recording.stdout], [], [], 5)[0]:
            raise TimeoutError("recorder did not report its PID")
        pid = recording.stdout.readline().strip()
        if not pid.isdecimal():
            raise RuntimeError("unexpected recorder PID")
        time.sleep(1)
        command = [sys.executable, "-m", "gameqa", "run", "--project",
                   str(Path(__file__).resolve().parents[1]), "--case", args.case,
                   "--kind", "ui", "--rounds", "1", "--report-dir", str(args.report_dir.resolve())]
        if args.config:
            command.extend(["--config", args.config])
        result = subprocess.run(command)
    finally:
        if pid and pid.isdecimal():
            subprocess.run(prefix + ["shell", "kill", "-2", pid], check=False)
        try:
            recording.wait(timeout=10)
        except subprocess.TimeoutExpired:
            recording.terminate()
            recording.wait(timeout=5)
    args.video.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(prefix + ["pull", remote, str(args.video.resolve())], check=True)
    subprocess.run(prefix + ["shell", "rm", remote], check=True)
    if args.video.stat().st_size == 0:
        raise RuntimeError("recording is empty")
    print(f"Recorded actual UI execution: {args.video.resolve()}")
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
