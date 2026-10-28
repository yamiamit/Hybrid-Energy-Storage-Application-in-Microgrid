"""
Save the current Claude Code conversation as a readable Markdown file.

Run by the Stop hook in .claude/settings.local.json after every reply.
Claude Code passes the hook a JSON object on stdin that names the session's
transcript file. Each session gets its own file in resources/chat_history/,
rewritten in full every time, so it is always up to date.

Can also be run by hand on a transcript file:
    python3 .claude/hooks/export_chat.py path/to/session.jsonl
"""

import json
import os
import re
import sys

PROJECT = os.environ.get("CLAUDE_PROJECT_DIR") or os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT_DIR = os.path.join(PROJECT, "resources", "chat_history")

# Internal text Claude Code adds to messages, which the reader doesn't need
HIDDEN = re.compile(r"<(system-reminder|ide_selection|ide_opened_file|ide_diagnostics|"
                    r"command-[a-z-]+|local-command-[a-z-]+|task-notification)>.*?</\1>", re.S)


def clean(text):
    return HIDDEN.sub("", text).strip()


def export(transcript):
    lines, started, session = [], None, None
    for raw in open(transcript, encoding="utf-8"):
        try:
            e = json.loads(raw)
        except ValueError:
            continue
        if e.get("type") not in ("user", "assistant") or e.get("isSidechain"):
            continue
        session = session or e.get("sessionId")
        content = (e.get("message") or {}).get("content")
        blocks = [{"type": "text", "text": content}] if isinstance(content, str) else (content or [])

        if e["type"] == "user":
            text = "\n\n".join(clean(b.get("text", "")) for b in blocks
                               if b.get("type") == "text").strip()
            if not text or e.get("isMeta") or text.startswith("[SYSTEM NOTIFICATION"):
                continue
            if text.startswith("This session is being continued from a previous conversation"):
                lines += ["---", "", "*(The conversation got long, so Claude summarised the "
                          "earlier part here and carried on.)*", ""]
                continue
            stamp = (e.get("timestamp") or "")[:16].replace("T", " ")
            started = started or stamp
            lines += ["---", "", f"## You  ·  {stamp} UTC", "", text, ""]
        else:
            for b in blocks:
                if b.get("type") == "text" and b.get("text", "").strip():
                    lines += ["### Claude", "", b["text"].strip(), ""]
                elif b.get("type") == "tool_use":
                    i = b.get("input") or {}
                    what = (i.get("description") or i.get("file_path") or i.get("query")
                            or i.get("url") or i.get("skill") or "")
                    lines += [f"*▸ {b.get('name')}: {what}*".replace("**", ""), ""]

    if not started:
        return None
    header = ["# BTP chat with Claude", "",
              f"Session started {started} UTC. Your messages and Claude's replies in order; "
              "actions Claude took (running code, editing files) are one-line notes in italics.", ""]
    os.makedirs(OUT_DIR, exist_ok=True)
    out = os.path.join(OUT_DIR, f"{started[:10]}_{(session or 'session')[:8]}.md")
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(header + lines) + "\n")
    return out


if __name__ == "__main__":
    if len(sys.argv) > 1:
        path = sys.argv[1]
    else:
        path = json.load(sys.stdin).get("transcript_path")
    if path and os.path.exists(path):
        print(export(path))
