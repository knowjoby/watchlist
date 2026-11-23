# Watchlist

Movies and web series, published from an Obsidian folder: https://knowjoby.github.io/watchlist/

`publish.py` mirrors the Journals plugin's Movies & Series tab (captures, reviews in `Series and Movies`, Rotten Tomatoes picks) plus the `🎬 Watchlist` folder.
Allow-listed fields only (title, type, platform, date, minutes, progress, episodes, status, rating/10, year, take, poster URL). Never note bodies, URLs or IDs; Journal-category notes are skipped.
A hand-made note with `publish: false` and a matching title hides an auto-captured title. `--dry-run` previews.

## Two-way ratings and status

- **On the site:** open `/watchlist/#owner` to see "Owner sign-in" (hidden from visitors). It asks for a fine-grained GitHub token with *Contents: read & write* on this repo only. It's kept in that browser's localStorage. Edits are appended to `edits.json`.
- **On the Mac:** `publish.py` (launchd, every 5 min) pulls `edits.json`, writes `Status`/`Rating` + `Review updated` into review notes in `Jobs life/Series and Movies` (creating one if needed; Rotten Tomatoes notes get `status`/`my_rating`), clears `edits.json`, then republishes. Newest `Review updated` wins.
- **In Obsidian:** the Journals plugin's Movies & Series cards have *Viewing status* and *Your rating* (1–10) pickers that write the same fields.
