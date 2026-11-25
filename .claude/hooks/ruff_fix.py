"""PostToolUse: format and lint-fix an edited Python file with the project's ruff.

What ruff cannot fix is sent back to the model (exit 2) so it is corrected in the same turn,
not at commit time.
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

RUFF_VERSION = "0.15.15"  # keep in sync with .pre-commit-config.yaml


def find_ruff(start: Path) -> list[str]:
    """The venv ruff of this checkout or of the main checkout; else a pinned uvx ruff."""
    roots: list[Path] = []
    try:
        out = subprocess.run(
            [
                "git",
                "-C",
                str(start),
                "rev-parse",
                "--path-format=absolute",
                "--show-toplevel",
                "--git-common-dir",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        ).stdout.split("\n")
        if len(out) >= 2 and out[0] and out[1]:
            roots = [Path(out[0]), Path(out[1]).parent]
    except (OSError, subprocess.SubprocessError):
        pass
    for root in roots:
        for exe in ("Scripts/ruff.exe", "bin/ruff"):
            candidate = root / "isp-customer-service" / ".venv" / exe
            if candidate.exists():
                return [str(candidate)]
    if shutil.which("uvx"):
        return ["uvx", f"ruff@{RUFF_VERSION}"]
    return []


def main() -> None:
    payload = json.load(sys.stdin)
    data = payload.get("tool_input") or {}
    path = Path(data.get("file_path") or "")
    if path.suffix != ".py" or not path.exists():
        return
    ruff = find_ruff(path.parent)
    if not ruff:
        print("ruff not found; file left unformatted", file=sys.stderr)
        return
    subprocess.run([*ruff, "check", "--fix", "--quiet", str(path)], capture_output=True)
    subprocess.run([*ruff, "format", "--quiet", str(path)], capture_output=True)
    left = subprocess.run(
        [*ruff, "check", "--output-format", "concise", str(path)],
        capture_output=True,
        text=True,
    )
    if left.returncode != 0:
        print(
            f"ruff found issues it cannot fix:\n{left.stdout.strip()}", file=sys.stderr
        )
        sys.exit(2)


if __name__ == "__main__":
    main()
