#!/usr/bin/env python3
"""Export ONLY allow-listed frontmatter fields from the vault's Watchlist folder
to watchlist.json, then commit and push if it changed. Note bodies are never read."""
import json, pathlib, re, subprocess, sys
from datetime import datetime, timezone

import os
VAULT_DIR = pathlib.Path(os.environ.get("WATCHLIST_DIR") or pathlib.Path.home() / "Desktop/jwriteshere/Jobs life/🏡 Life/🎬 Watchlist")
REPO = pathlib.Path(__file__).resolve().parent
OUT = REPO / "watchlist.json"
TYPES = {"movie", "series"}
STATUSES = {"want", "watching", "watched"}
LIMITS = {"title": 100, "platform": 40, "take": 200}


def frontmatter(path):
    with path.open(encoding="utf-8") as f:
        if f.readline().strip() != "---":
            return {}
        fm = {}
        for line in f:
            if line.strip() == "---":
                return fm
            m = re.match(r"^([A-Za-z]+):\s*(.*)$", line.rstrip("\n"))
            if m:
                fm[m.group(1).lower()] = m.group(2).strip().strip("\"'").strip()
    return {}


def clean(fm):
    if fm.get("publish", "true").lower() == "false":
        return None
    t, title = fm.get("type", "").lower(), fm.get("title", "")
    if t not in TYPES or not title:
        return None
    item = {"title": title[:LIMITS["title"]], "type": t}
    if fm.get("platform"):
        item["platform"] = fm["platform"][:LIMITS["platform"]]
    if re.fullmatch(r"(19|20)\d\d", fm.get("year", "")):
        item["year"] = int(fm["year"])
    s = fm.get("status", "").lower()
    item["status"] = s if s in STATUSES else "want"
    if re.fullmatch(r"[1-5]", fm.get("rating", "")):
        item["rating"] = int(fm["rating"])
    if fm.get("take"):
        item["take"] = fm["take"][:LIMITS["take"]]
    return item


def main():
    dry = "--dry-run" in sys.argv
    if not VAULT_DIR.is_dir():
        sys.exit(f"Watchlist folder not found: {VAULT_DIR}")
    items = [i for p in sorted(VAULT_DIR.glob("*.md")) if (i := clean(frontmatter(p)))]
    order = {"watching": 0, "watched": 1, "want": 2}
    items.sort(key=lambda i: (order[i["status"]], i["title"].lower()))
    if dry:
        print(json.dumps(items, indent=2, ensure_ascii=False))
        return
    old = json.loads(OUT.read_text()).get("items") if OUT.exists() else None
    if old == items:
        print("No changes.")
        return
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    OUT.write_text(json.dumps({"updated": stamp, "items": items}, indent=2, ensure_ascii=False) + "\n")
    git = lambda *a: subprocess.run(["git", "-C", str(REPO), *a], check=True)
    git("add", "watchlist.json")
    git("commit", "-q", "-m", f"Update watchlist ({len(items)} titles)")
    git("push", "-q")
    print(f"Published {len(items)} titles.")


if __name__ == "__main__":
    main()
