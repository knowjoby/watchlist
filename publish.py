#!/usr/bin/env python3
"""Publish ONLY allow-listed fields of movies and series to watchlist.json, then commit and push.

Mirrors the Journals plugin's "Movies & Series" tab. Sources (frontmatter only, never note bodies):
  1. ObsidianCapture's Media Log/Watching notes: Series, Movie, and unsorted (Other) viewing items. YouTube is skipped.
  2. Review notes in "Jobs life/Series and Movies" (merged into the captured title when they match).
     Notes categorised Journal/Reflection are skipped: their titles are personal.
  3. Rotten Tomatoes watchlist notes in the same folder (source: rotten-tomatoes).
  4. Hand-made notes in the Jobs life vault's Watchlist folder. `publish: false` there hides a title.
Published fields: title, type, platform, date, minutes, progress, episodes, status, rating (out of 10), year, take, poster URL.
"""
import json, os, pathlib, re, subprocess, sys
from datetime import datetime, timezone

HOME = pathlib.Path.home()
CAPTURE = HOME / "Library/Application Support/ObsidianCapture"
MANUAL_DIR = pathlib.Path(os.environ.get("WATCHLIST_DIR") or HOME / "Desktop/jwriteshere/Jobs life/🏡 Life/🎬 Watchlist")
REPO = pathlib.Path(__file__).resolve().parent
OUT = REPO / "watchlist.json"
POSTER_HOSTS = ("nflxso.net", "nflximg.net", "media-amazon.com", "hotstar.com", "primevideo.com", "flixster.com")
KINDS = {"movie": "movie", "movies": "movie", "film": "movie", "films": "movie", "series": "series", "tv": "series",
         "tvshow": "series", "tvshows": "series", "tvseries": "series", "seriestvshow": "series", "television": "series",
         "video": "video", "videos": "video", "youtube": "video", "other": "unsorted"}
STATUS = {"watching": "watching", "watched": "watched", "completed": "watched", "finished": "watched",
          "to-watch": "want", "watchlist": "want", "want": "want"}


def frontmatter(path):
    try:
        f = path.open(encoding="utf-8")
    except OSError:
        return {}
    with f:
        if f.readline().strip() != "---":
            return {}
        fm = {}
        for line in f:
            if line.strip() == "---":
                return fm
            m = re.match(r"^([^:\s][^:]*):\s*(.*)$", line.rstrip("\n"))
            if m:
                v = m.group(2).strip()
                try:
                    v = json.loads(v)
                except ValueError:
                    v = v.strip("\"'")
                fm[m.group(1).strip().lower()] = v
    return {}


def toks(v):
    v = v if isinstance(v, list) else str(v).split("/") if v else []
    return [re.sub(r"[^a-z0-9]", "", str(x).lower()) for x in v]


def kind_of(fm):
    for t in toks(fm.get("entry type")):
        if t in KINDS:
            return KINDS[t]
    tags = fm.get("tags")
    tags = re.split(r"[,\s]+", tags) if isinstance(tags, str) else tags
    for t in toks(fm.get("category")) + toks(tags):
        if KINDS.get(t) in ("movie", "series"):
            return KINDS[t]
    return None


def norm(title):
    t = re.sub(r"^the\s+", "", str(title).lower())
    t = re.sub(r"\s*[-–—]?\s*(season|series)\s+\d+.*$|\s*-\s*s\d+$", "", t)
    return re.sub(r"[^a-z0-9]", "", t)


def vault():
    try:
        return pathlib.Path(json.loads((CAPTURE / "config.json").read_text())["vault"])
    except (OSError, KeyError, ValueError):
        return None


def safe_url(url):
    url = str(url or "")
    host = re.sub(r"^https://([^/]+)/.*$", r"\1", url).lower()
    return url if url.startswith("https://") and any(host == h or host.endswith("." + h) for h in POSTER_HOSTS) else None


def poster(cover):
    if not isinstance(cover, str) or "Media Log/Artwork/" not in cover:
        return None
    key = pathlib.Path(cover.strip("[]")).stem
    try:
        return safe_url(json.loads((CAPTURE / "artwork-cache" / f"{key}.json").read_text()).get("image"))
    except (OSError, ValueError):
        return None


def num(v):
    try:
        n = float(str(v).split("/")[0].strip())
    except (ValueError, TypeError):
        return None
    return n if n == n else None


def date_of(v):
    m = re.match(r"\d{4}-\d\d-\d\d", str(v or ""))
    return m.group(0) if m else None


def base(title, kind):
    return {"title": str(title).strip()[:100], "type": kind, "status": "logged"}


def captured(fm):
    k = kind_of(fm)
    if k == "video" or (k not in ("movie", "series") and fm.get("viewing item") is not True):
        return None
    if fm.get("capture source") != "Obsidian Capture" or fm.get("viewing active") is False or not fm.get("title"):
        return None
    i = base(fm["title"], k if k in ("movie", "series") else "unsorted")
    i["status"] = STATUS.get(str(fm.get("status", "")).lower(), "logged")
    if fm.get("platform"):
        i["platform"] = str(fm["platform"])[:40]
    if (d := date_of(fm.get("date"))):
        i["date"] = d
    if (n := num(fm.get("played minutes"))):
        i["minutes"] = round(n)
    if (n := num(fm.get("completion %"))) is not None:
        i["progress"] = max(0, min(100, round(n)))
    if (n := num(fm.get("episodes finished"))):
        i["episodes"] = int(n)
    if (p := poster(fm.get("cover"))):
        i["poster"] = p
    return i


def review(fm, stem):
    if set(toks(fm.get("category"))) & {"journal", "reflection"}:
        return None
    k = kind_of(fm)
    if k not in ("movie", "series"):
        return None
    i = base(fm.get("title") or stem, k)
    i["status"] = STATUS.get(str(fm.get("status", "")).lower(), "logged")
    if fm.get("platform"):
        i["platform"] = str(fm["platform"])[:40]
    if (d := date_of(fm.get("date"))):
        i["date"] = d
    if (n := num(fm.get("rating") or fm.get("my_rating"))) and 0 < n <= 10:
        i["rating"] = round(n, 1)
    if (p := poster(fm.get("cover"))):
        i["poster"] = p
    return i


def rotten(fm, stem):
    i = base(fm.get("title") or stem.replace("+", " "), "movie" if str(fm.get("type")).lower() == "movie" else "series")
    i["status"] = STATUS.get(str(fm.get("status", "")).lower(), "want")
    if re.fullmatch(r"(19|20)\d\d", str(fm.get("year", ""))):
        i["year"] = int(fm["year"])
    if (d := date_of(fm.get("date_watched") or fm.get("date_added"))):
        i["date"] = d
    if (n := num(fm.get("my_rating"))) and 0 < n <= 10:
        i["rating"] = round(n, 1)
    if (p := safe_url(fm.get("poster"))):
        i["poster"] = p
    return i


def manual(fm):
    t, title = str(fm.get("type", "")).lower(), str(fm.get("title", "")).strip()
    if t not in ("movie", "series") or not title:
        return None
    i = base(title, t)
    i["status"] = STATUS.get(str(fm.get("status", "")).lower(), "want")
    if fm.get("platform"):
        i["platform"] = str(fm["platform"])[:40]
    if re.fullmatch(r"(19|20)\d\d", str(fm.get("year", ""))):
        i["year"] = int(fm["year"])
    if re.fullmatch(r"[1-5]", str(fm.get("rating", ""))):
        i["rating"] = int(fm["rating"]) * 2
    if fm.get("take"):
        i["take"] = str(fm["take"])[:200]
    return i


def merge(items, new, fuzzy=False):
    """Group like the Journals plugin: type + exact title. Reviews (fuzzy) attach to one captured title of the same type."""
    key = new["type"] + ":" + new["title"].lower().strip()
    if fuzzy and key not in items:
        hits = [k for k, i in items.items() if i["type"] == new["type"] and norm(i["title"]) == norm(new["title"])]
        if len(hits) == 1:
            key = hits[0]
    old = items.get(key)
    if not old:
        items[key] = new
        return
    m = {**old, **{k: v for k, v in new.items() if k not in ("title", "type", "status", "date", "poster")}}
    if new["status"] != "logged":
        m["status"] = new["status"]
    if new.get("date", "") > old.get("date", ""):
        m["date"] = new["date"]
    if not old.get("poster") and new.get("poster"):
        m["poster"] = new["poster"]
    items[key] = {k: v for k, v in m.items() if v is not None}


def collect():
    items, v = {}, vault()
    if v:
        caps = sorted((i for p in (v / "Jobs life/Media Log/Watching").glob("*.md") if (i := captured(frontmatter(p)))),
                      key=lambda i: i.get("date", ""))
        for i in caps:
            merge(items, i)
        for p in sorted((v / "Jobs life/Series and Movies").rglob("*.md")):
            fm = frontmatter(p)
            if fm.get("capture source") == "Obsidian Capture":
                continue
            if fm.get("source") == "rotten-tomatoes":
                i = rotten(fm, p.stem)
                items.setdefault(i["type"] + ":" + i["title"].lower().strip(), i)
            elif (i := review(fm, p.stem)):
                merge(items, i, fuzzy=True)
    if MANUAL_DIR.is_dir():
        for p in MANUAL_DIR.glob("*.md"):
            fm = frontmatter(p)
            if str(fm.get("publish", "")).lower() == "false" and fm.get("title"):
                k = norm(fm["title"])
                for key in [x for x, i in items.items() if norm(i["title"]) == k]:
                    items.pop(key)
            elif (i := manual(fm)):
                merge(items, i, fuzzy=True)
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
