#!/usr/bin/env python3
"""Build the controlled +1 gold cheese defect in a separate runtime; do not start it."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess

PROJECT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-dir", type=Path, default=Path(os.environ.get("GAMEQA_WORK_DIR", PROJECT / "../../work")))
    args = parser.parse_args()
    work = args.work_dir.resolve()
    base = work / "stendhal"
    original = base / "runtime"
    fault = base / "runtime-fault"
    java = Path(os.environ.get("STENDHAL_JAVA", work / "tools/zulu21.40.17-ca-jdk21.0.6-macosx_aarch64/zulu-21.jdk/Contents/Home/bin/java"))
    if not (original / "server.ini").exists():
        raise RuntimeError("Run setup.py first")
    fault.mkdir(exist_ok=True)
    for folder in ("data", "js"):
        shutil.copytree(original / folder, fault / folder, dirs_exist_ok=True)
    for path in list(original.glob("*.jar")) + [original / "libs"]:
        link = fault / path.name
        if not link.exists():
            link.symlink_to(path, target_is_directory=path.is_dir())
    for folder in ("database", "home", "tmp"):
        (fault / folder).mkdir(exist_ok=True)
    ini = fault / "server.ini"
    if not ini.exists():
        text = (original / "server.ini").read_text()
        text = text.replace(str(original / "database/h2db"), str(fault / "database/h2db"))
        text = text.replace("tcp_port=32160", "tcp_port=32161").replace("http_port=8080", "http_port=8081")
        ini.write_text(text)
    classes = base / "fault/classes"
    classes.mkdir(parents=True, exist_ok=True)
    subprocess.run([str(java.with_name("javac")), "--release", "8", "-cp", f"{original / 'stendhal-server-1.49.jar'}:{original / 'libs/*'}", "-d", str(classes), str(PROJECT / "integrations/stendhal/defects/overcharge/SellerBehaviour.java")], check=True)
    print(f"Controlled defect built at {fault}; TCP32161/HTTP8081, independent database.")
    print("Start fault using start.sh fault; create local test accounts on TCP32161 before first testing.")
    print("Stop only fault with stop.sh fault; use main config for original regression. Original jars, business price, and assertions are unchanged.")


if __name__ == "__main__":
    main()
