# Watchlist

Movies and web series, published from an Obsidian folder: https://knowjoby.github.io/watchlist/

`publish.py` mirrors the Journals plugin's Movies & Series tab (captures, reviews in `Series and Movies`, Rotten Tomatoes picks) plus the `🎬 Watchlist` folder.
Allow-listed fields only (title, type, platform, date, minutes, progress, episodes, status, rating/10, year, take, poster URL). Never note bodies, URLs or IDs; Journal-category notes are skipped.
A hand-made note with `publish: false` and a matching title hides an auto-captured title. `--dry-run` previews.

## Ratings and status

Set them in Obsidian (Journals plugin → Movies & Series → *Viewing status* / *Your rating*). The site is read-only and shows them within 5 minutes.
`publish.py` still applies any entries in `edits.json` (newest `Review updated` wins), but the page no longer offers web editing.
