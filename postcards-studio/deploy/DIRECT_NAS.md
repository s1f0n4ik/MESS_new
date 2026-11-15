# Deploy Studio with direct NAS WebDAV delivery

Canonical repository: https://github.com/DyadyaYasha/MESS_Inheritance .
The PDF proportional-crop fix is included from `8f4df1a`.
Production domain: https://mess-studio.pro . Existing exhibition binaries need
`POSTCARDS_STUDIO_URL=https://mess-studio.pro` when launched; newly built desktop
backends use this domain by default. Existing account emails remain unchanged.

Set `STUDIO_DOMAIN` and `STUDIO_PUBLIC_URL` for the new host. Caddy obtains and
renews a Let's Encrypt certificate on ports 80/443. API, PostgreSQL and Yjs are
internal Docker services. Existing 3x-UI ports/services must be inventoried and
backed up before deployment; do not restart Docker or modify its VPN settings.

If an existing panel's acme.sh renewal uses standalone HTTP-01 on port 80,
switch that certificate's saved `Le_Webroot` to a dedicated host directory
after backing up its configuration. Mount the directory read-only in Caddy
using `STUDIO_LEGACY_ACME_WEBROOT` and set `STUDIO_LEGACY_ACME_HOST` to the
certificate's IP/host. Verify an external HTTP challenge-file request before
the next renewal. This avoids stopping Caddy or the panel for validation;
the panel retains its certificate paths and existing reload hook.

Configure secrets outside Git in the deployment's shared `.env`:

```
STUDIO_NAS_WEBDAV_URL=https://nas.example.org:5006/studio
STUDIO_NAS_USERNAME=...
STUDIO_NAS_PASSWORD=...
STUDIO_NAS_PATH=
```

The URL points to an existing WebDAV mount. `STUDIO_NAS_PATH` is an optional
relative subdirectory. HTTPS verification stays enabled. Direct NAS takes
precedence over legacy Yandex configuration; there is no fallback to Yandex
when a configured NAS fails.

A publication uploads the four PDFs and editable attachment, verifies every
uploaded file by size and SHA-256, writes its manifest and atomically moves a
temporary pointer to `current.json`. Mediation archives use
`Медиации/<project>/<revision>` and a separate `latest.json`; they never change
the exhibition release pointer. An upload/readback failure prevents pointer
activation. A failed mediation delivery keeps its editable server archive for
retry. PDF preparation and release delivery run outside the API event loop;
publications are serialized within the single API worker.

Before activation, test real upload/readback/MOVE using a dedicated relative
test directory. Do not publish a new exhibition release just to test delivery.
The approved release should be switched only as an explicit publishing action.

## Restore and merge current content

Restore the original PostgreSQL custom dump, data volume, collaboration volume
and PDF template. Generate new infrastructure secrets; existing application
password hashes remain in PostgreSQL. With API and collaboration stopped, run:

```
python deploy/merge-api-snapshot.py /path/to/studio-content-TIMESTAMP
python deploy/merge-api-snapshot.py /path/to/studio-content-TIMESTAMP --apply
```

The first invocation is a dry run. The overlay validates stable revisions,
account identities, shared-template revisions, history and asset collisions.
It retains accounts, old releases and archives, adds current editable content
and missing history/assets, and increments project-template revisions to create
fresh Yjs room names from the imported database. Original binary rooms remain
in the archived volume. Never reuse an old room over imported newer text.
An application marker under `data/migrations/` makes a completed overlay
idempotent. Back up the target first and rehearse the merge on a separate DB.

After starting, compare every imported document to its source snapshot, verify
staff logins, two-browser collaboration, PDFs and sync downloads, then make a
new complete database/data/Yjs backup. `/api/health` reports the deployed Git SHA
through `STUDIO_RELEASE_ID`. On a single-worker installation, keep the Uvicorn
worker count at one while relying on the publication lock.

Existing typography, optional divider visibility, integrated image outlines
and physical four-PC acceptance remain separate tasks; this deployment does
not claim those issues are fixed.
