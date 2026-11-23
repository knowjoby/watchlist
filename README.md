# Watchlist

Movies and web series, published from an Obsidian folder: https://knowjoby.github.io/watchlist/

`publish.py` reads only the frontmatter fields `title, type, platform, year, status, rating, take`
from notes in the vault's `🎬 Watchlist` folder, never note bodies, writes `watchlist.json`, and
pushes if anything changed. `python3 publish.py --dry-run` shows what would be published.
