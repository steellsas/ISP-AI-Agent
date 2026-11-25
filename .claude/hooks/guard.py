"""PreToolUse guard: no reading of .env files, no commits or pushes on develop/main.

Reads the hook payload on stdin. A refusal is returned as a permissionDecision "deny" with the
reason, so the model sees why and can take the allowed route (a branch, a worktree).
"""

import json
import re
import shlex
import subprocess
import sys

PROTECTED_BRANCHES = {"develop", "main", "master"}
ENV_TEMPLATES = {".env.example", ".env.sample", ".env.template"}
# `.env` or `.env.local` as a path token; `.env.example` and words like `.venv` do not match.
ENV_TOKEN = re.compile(r"(?:^|[\s/\\'\"=:(])\.env(?:\.[\w-]+)?(?=$|[\s'\");|&>])")


def deny(reason: str) -> None:
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": reason,
                }
            }
        )
    )
    sys.exit(0)


def is_env_file(path: str) -> bool:
    name = re.split(r"[\\/]", path.strip().strip("\"'"))[-1].lower()
    if name in ENV_TEMPLATES:
        return False
    return name == ".env" or (name.startswith(".env.") and name not in ENV_TEMPLATES)


def mentions_env_file(command: str) -> bool:
    for match in ENV_TOKEN.finditer(command):
        token = match.group(0).lstrip(" \t\n/\\'\"=:(")
        if token.lower() not in ENV_TEMPLATES:
            return True
    return False


def target_dir(command: str, cwd: str) -> str:
    """The directory a git command runs in: `git -C <dir>`, else a leading `cd <dir> &&`."""
    m = re.search(r"\bgit\s+-C\s+(\"[^\"]+\"|'[^']+'|\S+)", command)
    if m:
        return m.group(1).strip("\"'")
    m = re.match(
        r"\s*(?:cd|Set-Location)\s+(\"[^\"]+\"|'[^']+'|\S+)\s*(?:&&|;)", command
    )
    if m:
        return m.group(1).strip("\"'")
    return cwd


def windows_path(path: str) -> str:
    """Git Bash spells C:\\x as /c/x; Windows git does not read that form."""
    m = re.match(r"^/([a-zA-Z])(/.*)?$", path)
    if m and sys.platform == "win32":
        return f"{m.group(1).upper()}:{m.group(2) or '/'}"
    return path


def current_branch(directory: str) -> str:
    directory = windows_path(directory)
    try:
        out = subprocess.run(
            ["git", "-C", directory, "branch", "--show-current"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return out.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def check_git(command: str, cwd: str) -> None:
    dash_c = r"(?:\s+-C\s+(?:\"[^\"]+\"|'[^']+'|\S+))?"
    commits = re.search(rf"\bgit\b{dash_c}\s+commit\b", command)
    pushes = re.search(rf"\bgit\b{dash_c}\s+push\b(.*)", command)
    if not (commits or pushes):
        return
    branch = current_branch(target_dir(command, cwd))
    if commits and branch in PROTECTED_BRANCHES:
        deny(
            f"Commit refused: the checkout is on '{branch}'. "
            "Create a branch (or a worktree) first; develop/main change only through PRs."
        )
    if pushes:
        try:
            args = shlex.split(pushes.group(1).split("&&")[0].split(";")[0])
        except ValueError:
            args = pushes.group(1).split()
        refs = [a.split(":")[-1] for a in args if not a.startswith("-")][1:]
        if any(r in PROTECTED_BRANCHES for r in refs) or (
            not refs and branch in PROTECTED_BRANCHES
        ):
            deny(
                "Push refused: develop/main change only through PRs that Andrius merges."
            )


def main() -> None:
    payload = json.load(sys.stdin)
    tool = payload.get("tool_name", "")
    data = payload.get("tool_input") or {}
    cwd = payload.get("cwd") or "."

    if tool in ("Read", "Edit", "Write", "MultiEdit", "NotebookEdit"):
        path = data.get("file_path") or data.get("notebook_path") or ""
        if is_env_file(path):
            deny(
                "Reading or changing .env is not allowed: it holds secrets. Ask Andrius."
            )
    elif tool in ("Grep", "Glob"):
        if is_env_file(data.get("path") or "") or ".env" in (data.get("glob") or ""):
            deny("Searching .env is not allowed: it holds secrets.")
    elif tool in ("Bash", "PowerShell"):
        command = data.get("command") or ""
        if mentions_env_file(command):
            deny(
                "Commands that touch .env are not allowed: it holds secrets. "
                "To check a key exists, ask Andrius."
            )
        check_git(command, cwd)


if __name__ == "__main__":
    main()
