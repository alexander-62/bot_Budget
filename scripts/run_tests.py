"""Run each test module in isolation; never run the live test_google.py probe."""
from pathlib import Path
import subprocess
import sys


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    modules = sorted((root / "tests").glob("test_*.py"))
    modules = [path for path in modules if " (" not in path.name]
    if not modules:
        raise RuntimeError("No test modules found")
    failures = 0
    for path in modules:
        print(f"Running {path.name}", flush=True)
        result = subprocess.run(
            [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", path.name, "-v"],
            cwd=root,
        )
        failures += result.returncode != 0
    print(f"Modules: {len(modules)}; failed: {failures}")
    return int(bool(failures))


if __name__ == "__main__":
    raise SystemExit(main())
