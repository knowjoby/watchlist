#!/usr/bin/env python3
"""Publish ONLY allow-listed fields of movies and series to watchlist.json, then commit and push.

Sources (note bodies are never read, only frontmatter):
  1. ObsidianCapture's Media Log/Watching notes (auto-captured viewing), Entry type Series or Movie only.
  2. Hand-made notes in the Jobs life vault's Watchlist folder (override auto entries with the same title).
"""
import json, os, pathlib, re, subprocess, sys
from datetime import datetime, timezone

HOME = pathlib.Path.home()
CAPTURE = HOME / "Library/Application Support/ObsidianCapture"
MANUAL_DIR = pathlib.Path(os.environ.get("WATCHLIST_DIR") or HOME / "Desktop/jwriteshere/Jobs life/🏡 Life/🎬 Watchlist")
REPO = pathlib.Path(__file__).resolve().parent
OUT = REPO / "watchlist.json"
STATUSES = {"want", "watching", "watched", "logged"}
POSTER_HOSTS = ("nflxso.net", "nflximg.net", "media-amazon.com", "hotstar.com", "primevideo.com")


def frontmatter(path):
    with path.open(encoding="utf-8") as f:
        if f.readline().strip() != "---":
            return {}
        fm = {}
        for line in f:
            if line.strip() == "---":
                return fm
            m = re.match(r"^([^:]+):\s*(.*)$", line.rstrip("\n"))
            if m:
                v = m.group(2).strip()
                try:
                    v = json.loads(v)
                except ValueError:
                    v = v.strip("\"'")
                fm[m.group(1).strip().lower()] = v
    return {}


def media_log_dir():
    try:
        vault = json.loads((CAPTURE / "config.json").read_text())["vault"]
    except (OSError, KeyError, ValueError):
        return None
    d = pathlib.Path(vault) / "Jobs life/Media Log/Watching"
    return d if d.is_dir() else None


def poster(cover):
    if not isinstance(cover, str) or not cover:
        return None
    key = pathlib.Path(cover).stem
    try:
        url = json.loads((CAPTURE / "artwork-cache" / f"{key}.json").read_text()).get("image", "")
    except (OSError, ValueError):
        return None
    host = re.sub(r"^https://([^/]+)/.*$", r"\1", url).lower()
    return url if url.startswith("https://") and any(host == h or host.endswith("." + h) for h in POSTER_HOSTS) else None


def num(v):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def auto_item(fm):
    t = str(fm.get("entry type", "")).lower()
    title = str(fm.get("title", "")).strip()
    if t not in ("movie", "series") or not title:
        return None
    item = {"title": title[:100], "type": t, "status": "logged"}
    s = str(fm.get("status", "")).lower()
    item["status"] = {"watching": "watching", "watched": "watched", "watchlist": "want", "want": "want"}.get(s, "logged")
    if fm.get("platform"):
        item["platform"] = str(fm["platform"])[:40]
    if re.fullmatch(r"\d{4}-\d\d-\d\d", str(fm.get("date", ""))):
        item["date"] = fm["date"]
    if num(fm.get("played minutes")):
        item["minutes"] = round(fm["played minutes"])
    if num(fm.get("completion %")) is not None:
        item["progress"] = max(0, min(100, round(fm["completion %"])))
    if num(fm.get("episodes finished")):
        item["episodes"] = int(fm["episodes finished"])
    if (p := poster(fm.get("cover"))):
        item["poster"] = p
    return item


def manual_item(fm):
    if str(fm.get("publish", "true")).lower() == "false":
        return None
    t, title = str(fm.get("type", "")).lower(), str(fm.get("title", "")).strip()
    if t not in ("movie", "series") or not title:
        return None
    item = {"title": title[:100], "type": t}
    if fm.get("platform"):
        item["platform"] = str(fm["platform"])[:40]
    if re.fullmatch(r"(19|20)\d\d", str(fm.get("year", ""))):
        item["year"] = int(fm["year"])
    s = str(fm.get("status", "")).lower()
    item["status"] = s if s in STATUSES - {"logged"} else "want"
    if re.fullmatch(r"[1-5]", str(fm.get("rating", ""))):
        item["rating"] = int(fm["rating"])
    if fm.get("take"):
        item["take"] = str(fm["take"])[:200]
    return item


def collect():
    items = {}
    if (d := media_log_dir()):
        for p in d.glob("*.md"):
            if (i := auto_item(frontmatter(p))):
                k = i["title"].lower()
                if k not in items or i.get("date", "") > items[k].get("date", ""):
                    items[k] = i
    if MANUAL_DIR.is_dir():
        for p in MANUAL_DIR.glob("*.md"):
            fm = frontmatter(p)
            if str(fm.get("publish", "")).lower() == "false" and fm.get("title"):
                items.pop(str(fm["title"]).strip().lower(), None)
            elif (i := manual_item(fm)):
                items[i["title"].lower()] = {**items.get(i["title"].lower(), {}), **i}
    return sorted(items.values(), key=lambda i: (i.get("date", ""), i["title"].lower()), reverse=True)


def main():
    items = collect()
    if "--dry-run" in sys.argv:
        print(json.dumps(items, indent=2, ensure_ascii=False))
        print(f"{len(items)} titles", file=sys.stderr)
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
