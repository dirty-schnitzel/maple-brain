"""How this project's Claude Code sessions use their context: the numbers claude_architecture.md is judged by.

Reads the session transcripts Claude Code keeps on this machine (~/.claude/projects/<project>/*.jsonl; the
sessions started in a worktree of this repo are in folders with the same prefix) and prints aggregates only -
nothing of a conversation's text beyond a count of sessions that opened by reading the handoff.

    .venv\\Scripts\\python tools\\claude\\session_stats.py                       # everything
    .venv\\Scripts\\python tools\\claude\\session_stats.py --since 2026-11-22    # the sessions begun since that day
    .venv\\Scripts\\python tools\\claude\\session_stats.py --until 2026-11-21    # ... or before it (the "before" numbers)

"Context" = the tokens a request sends to the model (everything the session has read and said so far); every
step of a session is one request, so a long session re-sends its whole context hundreds of times.
"""
import argparse
import glob
import json
import os
import re
import statistics
import subprocess


def project_dirs():
    """The transcript folders of this repo: the main checkout's and its worktrees'."""
    common = subprocess.run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
                            capture_output=True, text=True, check=True).stdout.strip()
    root = os.path.dirname(common)                       # .../maple-work/.git -> .../maple-work
    name = re.sub(r"[^A-Za-z0-9]", "-", os.path.normpath(root))
    return sorted(glob.glob(os.path.join(os.path.expanduser("~"), ".claude", "projects", name + "*")))


def text_of(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text")
    return ""


def read_session(path):
    s = {"ctx": [], "first_ts": None, "first_prompt": None, "compactions": 0, "tools": {}, "inline_py": 0, "shell": 0}
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            if not line.startswith('{"parentUuid"'):     # the other record kinds are bookkeeping, some of them huge
                continue
            try:
                o = json.loads(line)
            except ValueError:
                continue
            if o.get("isSidechain"):                     # a subagent's own steps
                continue
            s["first_ts"] = s["first_ts"] or o.get("timestamp")
            kind, msg = o.get("type"), o.get("message") or {}
            if kind == "system" and o.get("subtype") == "compact_boundary":
                s["compactions"] += 1
            elif kind == "user" and not o.get("isMeta") and s["first_prompt"] is None:
                t = re.sub(r"<[a-z-]+>.*?</[a-z-]+>", "", text_of(msg.get("content")), flags=re.S).strip()
                s["first_prompt"] = t or None
            elif kind == "assistant" and msg.get("model") != "<synthetic>":
                u = msg.get("usage") or {}
                ctx = sum(u.get(k) or 0 for k in ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"))
                if ctx:
                    s["ctx"].append(ctx)
                for b in msg.get("content") or []:
                    if isinstance(b, dict) and b.get("type") == "tool_use":
                        name = b.get("name", "?")
                        s["tools"][name] = s["tools"].get(name, 0) + 1
                        if name in ("Bash", "PowerShell"):
                            s["shell"] += 1
                            cmd = str((b.get("input") or {}).get("command", "")).lower()
                            s["inline_py"] += bool(re.search(r"python(\.exe)?\"? +-c\b|python(\.exe)? +(-i +)?- ?<<|<<'?(eof|py)", cmd))
    return s


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--since", help="only sessions begun on or after this day (YYYY-MM-DD, UTC)")
    ap.add_argument("--until", help="only sessions begun before this day (YYYY-MM-DD, UTC)")
    a = ap.parse_args()
    sessions = []
    for d in project_dirs():
        for path in glob.glob(os.path.join(d, "*.jsonl")):
            s = read_session(path)
            day = (s["first_ts"] or "")[:10]
            if s["ctx"] and (not a.since or day >= a.since) and (not a.until or day < a.until):
                sessions.append(s)
    if not sessions:
        print("no sessions in that range")
        return
    ctx = [c for s in sessions for c in s["ctx"]]
    total = sum(ctx)
    per_session = sorted((sum(s["ctx"]) for s in sessions), reverse=True)
    top = max(1, len(sessions) // 6)
    tools = {}
    for s in sessions:
        for k, v in s["tools"].items():
            tools[k] = tools.get(k, 0) + v
    shell = sum(s["shell"] for s in sessions)
    opened = sum(1 for s in sessions if re.search(r"read (the |its )?(handoff|md)", (s["first_prompt"] or "")[:400], flags=re.I))
    days = sorted((s["first_ts"] or "")[:10] for s in sessions)
    print(f"sessions: {len(sessions)}   ({days[0]} .. {days[-1]})")
    print(f"requests (steps): {len(ctx):,}")
    print(f"context per request: average {total / len(ctx) / 1000:.0f}k tokens, median {statistics.median(ctx) / 1000:.0f}k")
    print(f"requests above 200k: {100 * sum(c > 200_000 for c in ctx) / len(ctx):.0f} %"
          f"   tokens that are the part above 200k: {100 * sum(max(0, c - 200_000) for c in ctx) / total:.0f} %")
    print(f"the largest {top} sessions (a sixth) hold {100 * sum(per_session[:top]) / total:.0f} % of all tokens")
    print(f"a session's first request: median {statistics.median(s['ctx'][0] for s in sessions) / 1000:.0f}k tokens;"
          f" its 10th: {statistics.median(s['ctx'][min(9, len(s['ctx']) - 1)] for s in sessions) / 1000:.0f}k")
    print(f"sessions that opened by reading the handoff: {opened} of {len(sessions)}")
    print(f"compactions: {sum(s['compactions'] for s in sessions)}   subagent calls: {tools.get('Agent', 0) + tools.get('Task', 0)}"
          f"   skill calls: {tools.get('Skill', 0)}")
    print(f"shell calls: {shell:,}, of them throwaway inline Python: {100 * sum(s['inline_py'] for s in sessions) / max(shell, 1):.0f} %")


if __name__ == "__main__":
    main()
