"""Offline heuristic audit. Reports locations, never matching secret values.

Scans candidate files and reachable local Git history. Does not open secret files.
Not a replacement for credential rotation or a full security review.
"""
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
PATTERNS = {
    "telegram-token": rb"\b\d{6,12}:[A-Za-z0-9_-]{30,}\b",
    "private-key": rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
    "google-api-key": rb"AIza[0-9A-Za-z_-]{30,}",
    "github-token": rb"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{30,})",
    "aws-access-key": rb"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b",
    "slack-token": rb"\bxox[baprs]-[A-Za-z0-9-]{20,}",
    "credential-url": rb"https?://[^\s/:]+:[^\s/@]+@",
    "literal-secret": rb'''(?im)^\s*["']?(?:BOT_TOKEN|password|api_key|client_secret|private_key)["']?\s*[:=]\s*["']([^"'\r\n]{16,})["']''',
}


def git(*args: str) -> bytes:
    return subprocess.check_output(["git", *args], cwd=ROOT, stderr=subprocess.PIPE)


def forbidden(path: str) -> bool:
    name = PurePosixPath(path).name.lower()
    return (
        name in {"secrets.py", "credentials.json", ".env", "bot.log"}
        or name.startswith(".env.") and name != ".env.example"
        or name.startswith("credentials") and name.endswith(".json")
        or "service-account" in name and name.endswith(".json")
        or name.endswith((".pem", ".key", ".log"))
    )


def scan(data: bytes, label: str) -> int:
    count = 0
    for kind, pattern in PATTERNS.items():
        for match in re.finditer(pattern, data):
            # JPEG default AC Huffman symbol table in a PNG provenance thumbnail.
            # Allow only this exact binary sequence, not arbitrary PNG contents.
            jpeg_symbols = b"456789:" + b"CDEFGHIJSTUVWXYZcdefghijstuvwxyz"
            if (kind == "telegram-token" and data.startswith(b"\x89PNG\r\n\x1a\n")
                    and match.group() == jpeg_symbols
                    and data[max(0, match.start()-4):match.start()] == b"'()*"):
                continue
            if kind == "literal-secret" and match.group(1).decode("utf-8", errors="replace") == "ваш_токен_бота":
                continue
            line = data.count(b"\n", 0, match.start()) + 1
            print(f"FINDING {kind}: {label}:{line}")
            count += 1
    return count


def main() -> int:
    paths = set(git("ls-files", "--cached", "--others", "--exclude-standard", "-z").decode("utf-8").split("\0")) - {""}
    findings = 0
    for path in sorted(paths):
        if forbidden(path):
            print(f"FINDING forbidden filename (not opened): {path}")
            findings += 1
        elif (ROOT / path).is_file():
            findings += scan((ROOT / path).read_bytes(), f"worktree/{path}")
    commits = git("rev-list", "--all").decode("ascii").splitlines()
    seen = set()
    for commit in commits:
        findings += scan(git("show", "-s", "--format=%B", commit), f"commit-message/{commit[:12]}")
        for entry in git("ls-tree", "-r", "-z", commit).split(b"\0"):
            if not entry:
                continue
            metadata, raw_path = entry.split(b"\t", 1)
            _, kind, oid = metadata.split()
            path = raw_path.decode("utf-8")
            if kind != b"blob":
                continue
            if forbidden(path):
                print(f"FINDING historical forbidden filename (not opened): {commit[:12]}/{path}")
                findings += 1
            elif oid not in seen:
                seen.add(oid)
                findings += scan(git("cat-file", "blob", oid.decode("ascii")), f"{commit[:12]}/{path}")
    print(f"Candidate files: {len(paths)}; commits: {len(commits)}; unique historical blobs: {len(seen)}; findings: {findings}")
    return int(bool(findings))


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except subprocess.CalledProcessError:
        print("Audit incomplete: Git command failed. Run inside a readable Git checkout.", file=sys.stderr)
        raise SystemExit(2)
