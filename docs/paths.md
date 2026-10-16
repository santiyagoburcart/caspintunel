# Admin-panel and reseller-portal paths

The admin panel (default `/panel/`) and the reseller portal (default `/agency/`) can live on any path of
the domain. Change them in **Settings → Paths** (super admin) or on the server with `./scripts/paths.sh`.

## How a change is applied

The web container has no docker access. It validates the request and writes `backups/.paths-request.json`.
A host cron job applies it within a minute:

```cron
* * * * * /root/caspintunel/scripts/paths.sh apply-request >> /var/log/caspintunel-paths.log 2>&1
```

`paths.sh` renders `nginx/paths/active.conf` from `nginx/paths.conf.template` (`nginx/render-paths.sh`,
the same renderer the nginx entrypoint uses for the defaults), runs `nginx -t`, reloads, and then verifies
through nginx itself: the admin page answers on the new path with the right `<base>`, the user site announces
the portal path, and the old `/panel/` answers 404. **Any failure restores the previous config.** The result
is written to `backups/.paths-status.json`, which the Settings page shows.

* Old admin path: **404, no redirect** (a moved panel is not revealed). The public site's "admin panel" link is
  only shown while the panel is on `/panel/`.
* Old portal path: just a page of the user site (redirects home).
* Rules (both checked server-side and by the renderer): `/` + 2–40 of `a-z 0-9 - _`; not a site path (`/api`,
  `/admin`, `/ws`, `/static`, `/media`, `/assets`, `/login`, `/register`, `/store`, …); admin ≠ portal; the
  portal cannot take `/panel`.

## How the SPAs follow

* Admin SPA is built with **relative assets** (`vite base './'`); nginx injects `<base href="/x/">` and
  `<meta name="ct-admin-base">`, which also sets the router basename (`src/lib/base.js`). The admin location keeps
  the locked-down CSP / X-Frame-Options.
* User SPA reads `<meta name="ct-portal-path">` and `<meta name="ct-admin-link">` (`src/lib/paths.js`), injected
  into every user-site HTML response.

## Recovery CLI (forgot the admin path?)

```bash
./scripts/paths.sh show                 # current paths, pending request, last result
./scripts/paths.sh reset                # back to /panel + /agency
./scripts/paths.sh set-admin /my-panel
./scripts/paths.sh set-portal /resellers
```

`nginx/paths/` (active.conf, paths.json) is git-ignored, so `./update.sh` keeps a custom path; `update.sh`
and `install.sh` run `paths.sh ensure`. Test: `./scripts/test-paths.sh` (throw-away stack, real nginx +
browser: default → move admin → move portal → request file → invalid request → rollback → reset).
