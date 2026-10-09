"""Measure report processing without connecting to a game or changing evidence."""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import statistics
import sys
import tempfile
import time


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, default=root / "src")
    parser.add_argument("--reports", type=Path, nargs="+", default=[
        root / "docs/evidence/stendhal-api-batch1/round-01/report.json",
        root / "docs/evidence/stendhal-quest-chain-final/round-01/report.json",
    ])
    parser.add_argument("--repeats", type=int, default=7)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.repeats < 1:
        parser.error("repeats must be positive")
    sys.path.insert(0, str(args.source_dir.resolve()))
    from gameqa.bridge import redact
    from gameqa.evidence import write_report

    inputs = [json.loads(path.read_text(encoding="utf-8")) for path in args.reports]
    records = [case for report in inputs for case in report["cases"]]
    metadata = {"benchmark": "frozen historical report rebuild"}
    payload = {"metadata": metadata, "cases": records}
    original = json.dumps(payload, ensure_ascii=False)
    samples = {"redact": [], "write_report": []}
    with tempfile.TemporaryDirectory(prefix="gameqa-benchmark-") as directory:
        folder = Path(directory)
        for iteration in range(args.repeats + 1):
            started = time.perf_counter()
            clean = redact(payload)
            redaction = time.perf_counter() - started
            started = time.perf_counter()
            write_report(folder, records, metadata)
            writing = time.perf_counter() - started
            if iteration:  # One warm-up is excluded for both implementations.
                samples["redact"].append(redaction)
                samples["write_report"].append(writing)
        assert json.dumps(payload, ensure_ascii=False) == original, "input was mutated"
        assert json.loads((folder / "report.json").read_text(encoding="utf-8")) == clean
        outputs = {name: hashlib.sha256((folder / name).read_bytes()).hexdigest()
                   for name in ("report.json", "index.html")}
    result = {"python": platform.python_version(), "platform": platform.platform(),
              "cases": len(records), "input_bytes": len(original.encode("utf-8")),
              "repeats": args.repeats, "warmups": 1,
              "inputs": [{"name": path.parent.parent.name,
                          "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
                         for path in args.reports],
              "source_sha256": {name: hashlib.sha256((args.source_dir / "gameqa" / name).read_bytes()).hexdigest()
                                for name in ("bridge.py", "evidence.py")},
              "output_sha256": outputs,
              "measurements": {name: {"seconds": values, "median_seconds": statistics.median(values)}
                               for name, values in samples.items()}}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"cases": result["cases"], "repeats": args.repeats,
                      "median_seconds": {name: row["median_seconds"]
                                         for name, row in result["measurements"].items()}}))


if __name__ == "__main__":
    main()
