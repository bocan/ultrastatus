# Running statusboard from cron

`make refresh` polls every provider, then renders `site/index.html`. It renders even when a provider fails, so the page always reflects the latest good data and shows which provider is stale. The exit code is the poll's exit code.

## Crontab line

```
*/2 * * * * cd /Users/chris/Play/statusboard && PATH=/opt/homebrew/bin:$PATH make refresh >> /tmp/statusboard.log 2>&1
```

Edit with `crontab -e`.

## The two things people get wrong

1. **Absolute paths.** Cron starts in your home directory with almost no environment. The `cd` must be absolute, and the database path defaults to `./statusboard.sqlite3` relative to that directory. Set `STATUSBOARD_DB=/absolute/path.sqlite3` in the crontab line if you want it elsewhere.
2. **`PATH` for `uv`.** Cron's `PATH` is usually `/usr/bin:/bin`. Homebrew installs `uv` under `/opt/homebrew/bin` on Apple silicon, or `/usr/local/bin` on Intel. The `PATH=` prefix on the line above fixes that. Check with `which uv`.

## Serving the page

`site/index.html` is one file with no external requests. Open it directly, or point any static file server at `site/`. The page reloads itself every two minutes through a meta refresh tag.

## Checking it works

```
tail -f /tmp/statusboard.log
```

Each run prints one line per provider and `wrote site/index.html`.
