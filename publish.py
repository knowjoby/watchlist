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
          "to-watch": "want", "watchlist": "want", "want": "want", "paused": "paused", "dropped": "dropped"}
NOTE_STATUS = {"want": "Watchlist", "watching": "Watching", "watched": "Watched", "paused": "Paused", "dropped": "Dropped", "logged": "Logged"}
RT_STATUS = {"want": "to-watch", "watching": "watching", "watched": "watched", "paused": "paused", "dropped": "dropped", "logged": "to-watch"}
EDITS = REPO / "edits.json"


READ_ERRORS = 0


def frontmatter(path):
    global READ_ERRORS
    try:
        f = path.open(encoding="utf-8")
    except OSError as e:
        READ_ERRORS += 1
        if READ_ERRORS == 1:
            print(f"Can't read {path.name}: {e}", file=sys.stderr)
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
    if (u := stamp_of(fm)):
        i["updated"] = u
    return i


def stamp_of(fm):
    u = str(fm.get("review updated") or "")
    return u if re.fullmatch(r"\d{4}-\d\d-\d\dT[\d:.]+Z", u) else None


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
    if (u := stamp_of(fm)):
        i["updated"] = u
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
    w = v / "Jobs life/Media Log/Watching" if v else None
    try:
        seen = len(os.listdir(w)) if w else "no vault"
    except OSError as e:
        seen = repr(e)
    print(f"{datetime.now():%Y-%m-%d %H:%M} vault={v is not None} watching files={seen}", file=sys.stderr)
    if v and not isinstance(seen, int):
        global READ_ERRORS
        READ_ERRORS += 1
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
    # Statuses/ratings the Journals plugin keeps in its own data (used for titles whose type isn't set yet).
    try:
        st = json.loads((v / ".obsidian/plugins/journal-date-organizer/data.json").read_text()) if v else {}
    except (OSError, ValueError):
        st = {}
    kinds = {"movie": "Movie", "series": "Series", "unsorted": "Other"}
    for i in items.values():
        k = kinds[i["type"]] + ":" + i["title"].lower().strip()
        if (s := STATUS.get(str((st.get("mediaStatuses") or {}).get(k, "")).lower())):
            i["status"] = s
        if (n := num((st.get("mediaRatings") or {}).get(k))) and 0 < n <= 10:
            i["rating"] = round(n, 1)
    # One show captured from two Prime pages ("Time" and "Time - Season 1") is one title, as in Journals.
    rank = lambda i: (i["status"] != "logged", bool(i.get("rating")), i.get("date", ""))
    groups = {}
    for k, i in items.items():
        if i["type"] in ("movie", "series") and norm(i["title"]):
            groups.setdefault((i["type"], norm(i["title"])), []).append(k)
    for keys in groups.values():
        if len(keys) < 2:
            continue
        keys.sort(key=lambda k: rank(items[k]), reverse=True)
        top = items[keys[0]]
        for k in keys[1:]:
            o = items.pop(k)
            for f in ("poster", "minutes", "progress", "episodes", "platform", "year", "take"):
                if f in o and f not in top:
                    top[f] = o[f]
            if o.get("date", "") > top.get("date", ""):
                top["date"] = o["date"]
    typed = {norm(i["title"]): i for i in items.values() if i["type"] != "unsorted"}
    for k, i in list(items.items()):
        if i["type"] == "unsorted" and (t := typed.get(norm(i["title"]))):
            for f in ("poster", "minutes", "progress", "episodes", "date", "platform"):
                if f in i and f not in t:
                    t[f] = i[f]
            del items[k]
    return sorted(items.values(), key=lambda i: (i.get("date", ""), i["title"].lower()), reverse=True)


def set_frontmatter(path, updates):
    """Replace/insert/remove scalar frontmatter keys (case-insensitive), leaving everything else untouched."""
    lines = path.read_text(encoding="utf-8").split("\n")
    end = lines.index("---", 1)
    for key, value in updates.items():
        idx = next((n for n in range(1, end) if re.match(re.escape(key) + r"\s*:", lines[n], re.I)), None)
        new = None if value is None else f"{key}: {json.dumps(value, ensure_ascii=False)}"
        if idx is None:
            if new:
                lines.insert(end, new)
                end += 1
            continue
        stop = idx + 1
        while stop < end and re.match(r"^\s+-|^\s{2,}\S", lines[stop]):
            stop += 1
        lines[idx:stop] = [new] if new else []
        end -= (stop - idx) - (1 if new else 0)
    path.write_text("\n".join(lines), encoding="utf-8")


def target_note(folder, edit):
    """The note a web edit belongs in: a Rotten Tomatoes pick or a personal review note; created if missing."""
    want = norm(edit["title"])
    for p in sorted(folder.rglob("*.md")):
        fm = frontmatter(p)
        if fm.get("capture source") == "Obsidian Capture" or set(toks(fm.get("category"))) & {"journal", "reflection"}:
            continue
        if fm.get("source") == "rotten-tomatoes":
            if norm(fm.get("title") or p.stem.replace("+", " ")) == want:
                return p, fm, True
        elif kind_of(fm) == edit["type"] and norm(fm.get("captured title") or fm.get("title") or p.stem) == want:
            return p, fm, False
    name = re.sub(r"\s+", " ", re.sub(r'[\\/:*?"<>|#^\[\]]', " ", edit["title"])).strip() or "Untitled"
    p = folder / f"{name}.md"
    if p.exists():
        return p, frontmatter(p), False
    p.write_text("---\n" + "\n".join(f"{k}: {json.dumps(v, ensure_ascii=False)}" for k, v in {
        "Title": edit["title"], "Captured title": edit["title"], "Entry type": edit["type"].capitalize(),
        "Category": "Movie" if edit["type"] == "movie" else "TVShow"}.items()) + f"\n---\n\n# {edit['title']}\n", encoding="utf-8")
    return p, {}, False


def apply_web_edits():
    """Pull owner edits made on the website (edits.json) into Obsidian notes; newest change wins."""
    git = lambda *a: subprocess.run(["git", "-C", str(REPO), *a], check=True, capture_output=True, text=True)
    git("pull", "-q", "--rebase")
    try:
        edits = json.loads(EDITS.read_text()).get("edits", [])
    except (OSError, ValueError):
        return 0
    v = vault()
    if not edits or not v:
        return 0
    folder = v / "Jobs life/Series and Movies"
    folder.mkdir(exist_ok=True)
    applied = 0
    for e in edits:
        if e.get("type") not in ("movie", "series") or not str(e.get("title", "")).strip() or not stamp_of({"review updated": e.get("updated")}):
            continue
        path, fm, rt = target_note(folder, e)
        if (stamp_of(fm) or "") >= e["updated"]:
            continue
        upd = {"Review updated": e["updated"]}
        if e.get("status") in NOTE_STATUS:
            upd["status" if rt else "Status"] = (RT_STATUS if rt else NOTE_STATUS)[e["status"]]
        if "rating" in e:
            r = e["rating"]
            upd["my_rating" if rt else "Rating"] = int(r) if isinstance(r, (int, float)) and 1 <= r <= 10 else None
        set_frontmatter(path, upd)
        applied += 1
    EDITS.write_text(json.dumps({"edits": []}, indent=2) + "\n")
    git("add", "edits.json")
    git("commit", "-q", "-m", f"Apply {len(edits)} web edit(s) to Obsidian")
    git("push", "-q")
    print(f"Applied {applied} of {len(edits)} web edit(s).")
    return applied


def main():
    if "--dry-run" not in sys.argv:
        apply_web_edits()
    items = collect()
    if "--dry-run" in sys.argv:
        print(json.dumps(items, indent=2, ensure_ascii=False))
        print(f"{len(items)} titles", file=sys.stderr)
        return
    old = json.loads(OUT.read_text()).get("items") if OUT.exists() else None
    if READ_ERRORS or (old and len(items) < len(old) * 0.6 and "--force" not in sys.argv):
        print(f"Not publishing: {len(items)} titles vs {len(old or [])} before, {READ_ERRORS} unreadable notes "
              "(vault offline or blocked?). Rerun with --force if the drop is real.")
        sys.exit(1)
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
