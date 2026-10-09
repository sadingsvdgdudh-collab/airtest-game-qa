#!/usr/bin/env python3
"""Fetch fixed official releases and prepare the isolated Stendhal runtime."""
import argparse
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import urllib.request
import zipfile

PROJECT = Path(__file__).resolve().parents[2]
COMMIT = "cbe0825e9b46f2a8adf9adce8c5747ece13b17a0"
RELEASES = {
    "stendhal-server-1.49.complete.zip": (
        "https://downloads.sourceforge.net/project/arianne/stendhal/1.49/stendhal-server-1.49.zip",
        "91bbede0ab3a52df94eeaa0eeea315285ccf9164ce3715b81f1dff808cf5051d",
    ),
    "stendhal-1.49.complete.zip": (
        "https://downloads.sourceforge.net/project/arianne/stendhal/1.49/stendhal-1.49.zip",
        "5e37fe00c11be6ead10eb12a406d2ab4ad2605943791d13cda5afa064c7f2e3c",
    ),
    "typescript-5.2.2.tgz": (
        "https://registry.npmjs.org/typescript/-/typescript-5.2.2.tgz",
        "52e30f921a2fb921adb594c61904e18762174d668bbc159a112cda98ef6ada0c",
    ),
}


def download(path, url, expected):
    if not path.exists():
        print(f"Downloading {path.name}", flush=True)
        partial = path.with_suffix(path.suffix + ".part")
        with urllib.request.urlopen(url, timeout=90) as response, partial.open("wb") as dest:
            shutil.copyfileobj(response, dest)
        partial.rename(path)
    with path.open("rb") as source:
        actual = hashlib.file_digest(source, "sha256").hexdigest()
    if actual != expected:
        raise RuntimeError(f"SHA256 mismatch: {path}; remove this file and retry")


def unpack_zip(archive, destination):
    with zipfile.ZipFile(archive) as bundle:
        invalid = bundle.testzip()
        if invalid:
            raise RuntimeError(f"CRC failed: {invalid}")
        for member in bundle.namelist():
            target = (destination / member).resolve()
            if not target.is_relative_to(destination.resolve()):
                raise RuntimeError(f"Unsafe archive member: {member}")
        bundle.extractall(destination)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-dir", type=Path, default=Path(os.environ.get("GAMEQA_WORK_DIR", PROJECT / "../../work")))
    parser.add_argument("--java", type=Path)
    parser.add_argument("--node", default=os.environ.get("STENDHAL_NODE", "node"))
    parser.add_argument("--download-jdk", action="store_true", help="Download portable macOS arm64 JDK21 when absent")
    args = parser.parse_args()
    work = args.work_dir.resolve()
    base = work / "stendhal"
    downloads = base / "downloads"
    downloads.mkdir(parents=True, exist_ok=True)
    java = args.java or Path(os.environ.get("STENDHAL_JAVA", work / "tools/zulu21.40.17-ca-jdk21.0.6-macosx_aarch64/zulu-21.jdk/Contents/Home/bin/java"))
    if not java.exists() and args.download_jdk:
        tools = work / "tools"
        tools.mkdir(parents=True, exist_ok=True)
        archive = tools / "zulu21.tar.gz"
        download(archive, "https://cdn.azul.com/zulu/bin/zulu21.40.17-ca-jdk21.0.6-macosx_aarch64.tar.gz", "1d6385f17ae2dc3b57a6d1b6fd6aeadafe1c7138bc744f62a767851eececd092")
        with tarfile.open(archive) as bundle:
            bundle.extractall(tools, filter="data")
    if not java.exists():
        raise RuntimeError("Provide --java /path/to/java or --download-jdk (macOS arm64)")
    for name, (url, digest) in RELEASES.items():
        download(downloads / name, url, digest)
    runtime = base / "runtime"
    runtime.mkdir(exist_ok=True)
    if not (runtime / "stendhal-server-1.49.jar").exists():
        unpack_zip(downloads / "stendhal-server-1.49.complete.zip", runtime)
    if not (base / "client/lib/stendhal-data.jar").exists():
        unpack_zip(downloads / "stendhal-1.49.complete.zip", base / "client")
    if not (base / "typescript/package/bin/tsc").exists():
        with tarfile.open(downloads / "typescript-5.2.2.tgz") as bundle:
            bundle.extractall(base / "typescript", filter="data")
    source = base / "source"
    if not (source / ".git").exists():
        subprocess.run(["git", "-c", "http.version=HTTP/1.1", "clone", "--depth", "1", "--branch", "v1.49", "--filter=blob:none", "--sparse", "https://github.com/arianne/stendhal.git", str(source)], check=True)
    commit = subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip()
    if commit != COMMIT:
        raise RuntimeError(f"Unexpected Stendhal source commit: {commit}")
    subprocess.run(["git", "-C", str(source), "-c", "http.version=HTTP/1.1", "sparse-checkout", "set", "src", "data/conf", "buildtools", "bin"], check=True)
    # Local web initialization repair; business behavior is unchanged.
    shutil.copy2(PROJECT / "integrations/stendhal/web_patch/ItemMap.ts", source / "src/js/stendhal/entity/ItemMap.ts")
    for folder in ("database", "home", "tmp"):
        (runtime / folder).mkdir(exist_ok=True)
    ini = runtime / "server.ini"
    if not ini.exists():
        subprocess.run([str(java), f"-Duser.home={runtime / 'home'}", "-cp", "stendhal-server-1.49.jar", "games.stendhal.server.core.engine.GenerateINI"], input="\n\n", text=True, cwd=runtime, check=True)
        # 顺带关掉 H2 的退出钩子：否则停服时它抢在 marauroa 写队列刷完之前关库，
        # 实测那一秒会产生 400+ 条 Database is already closed 加 rollback，等于丢写（曾把角色写坏）。
        text = ini.read_text().replace("jdbc:h2:~/stendhal/database/h2db", f"jdbc:h2:{runtime / 'database/h2db'}").replace(";AUTO_RECONNECT=TRUE", ";AUTO_RECONNECT=TRUE;DB_CLOSE_ON_EXIT=FALSE;WRITE_DELAY=500;CACHE_SIZE=131072")
        ini.write_text(text + "\n# Isolated local QA only\ntcp_host=127.0.0.1\nhttp_host=127.0.0.1\nhttp_port=8080\nallow_account_creation=true\nallow_character_creation=true\n")
    admin_file = runtime / "data/conf/admins.txt"
    admin_names = admin_file.read_text().splitlines()
    if "qaobserver" not in admin_names:
        admin_file.write_text("\n".join(admin_names + ["qaobserver"]) + "\n")
    patches = base / "patches/classes"
    patches.mkdir(parents=True, exist_ok=True)
    subprocess.run([str(java.with_name("javac")), "--release", "8", "-cp", str(runtime / "libs/*"), "-d", str(patches), str(PROJECT / "integrations/stendhal/network_patch/NIONetworkConnectionManager.java")], check=True)
    env = {**os.environ, "GAMEQA_WORK_DIR": str(work), "STENDHAL_JAVA": str(java), "STENDHAL_NODE": args.node}
    subprocess.run([str(PROJECT / "scripts/stendhal/compile_web.sh")], env=env, check=True)
    print(f"Runtime prepared: {runtime}; no server started and no existing database reset.")


if __name__ == "__main__":
    main()
