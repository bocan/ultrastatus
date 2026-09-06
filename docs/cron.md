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

## Slow polls

A poll that crawls, one provider line every 20 seconds or so, is almost always IPv6. The box has a v6 address but no v6 route, so every connection waits the full timeout on the v6 address before trying v4. The poller now prefers IPv4 addresses for every lookup. On a host where v6 works and you want it used, set `STATUSBOARD_IPV6=1` in the crontab line.

The other silent wait is the first `uv run` on a fresh machine, which downloads a Python build when the system one is older than 3.12. Run `make install` once by hand to watch it.

## Security headers

The page carries its Content-Security-Policy in a meta tag, but header scanners only read headers and `frame-ancestors` only works in one. `render` therefore also writes `site/csp.conf`, an nginx snippet with the same policy as a header plus `frame-ancestors 'self'`. Include it at server level, beside your other `add_header` lines and outside any `location` block:

```nginx
include /volume/ultrastatus/site/csp.conf;
```

The policy contains the hash of the inline script, so it changes when `map.js` changes. nginx reads the include only at start or reload, so after a `git pull` that touches the script, run `nginx -s reload`. Until then the stale header would block the new script, so make the reload part of the deploy step.

## Serving the page

`site/index.html` is one file with no external requests. Open it directly, or point any static file server at `site/`. The page reloads itself every two minutes through a meta refresh tag.

## Checking it works

```
tail -f /tmp/statusboard.log
```

Each run prints one line per provider and `wrote site/index.html`.
