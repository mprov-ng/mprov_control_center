---
type: Reference
title: mPCC Architecture Overview
description: Project layout, installed Django apps, URL routing map, environment configuration, container bootstrap, database and backup setup, and CI pipeline for the mProv Control Center repository.
tags: [mprov, django, architecture, routing, settings, ci, containers]
---

# Architecture Overview

mProv Control Center is a single Django project (`mprov_control_center/`, `django>=5.2.19,<6` — 5.2 LTS, moved from Django 4.2 with the Rocky Linux 9 / Python 3.12 image in #197) that combines an operator admin UI with a DRF JSON API. Almost all API behavior flows through one shared base class, [MProvView](api-foundation.md), and almost all external side effects flow through the [job queue](../domain/jobs-and-scripts.md) rather than direct calls.

## Project layout

```
mprov_control_center/   settings, root urlconf, wsgi, /datamodel/ view, index view
common/                 MProvView base class, shared serializers, AdminWizardModel, test helpers
authcustom/             custom User admin (re-registers django User with a custom change form)
systems/                Systems, NICs, BMCs, system images, groups — see Systems & Networking
networks/               Networks, network types, switches/ports — see Systems & Networking
jobqueue/               Jobs, job modules, jobservers — see Jobs & Scripts
scripts/                Scripts, files, Ansible playbooks/roles/collections — see Jobs & Scripts
osmanagement/         OS types, distros, repos — see OS & Disk Management
disklayouts/            Disk layouts, partitions, RAID — see OS & Disk Management
pki/                  Per-install CA, TLS issuance, agent client-cert auth, enrollment — see PKI & Agent Auth
utils/                  template tags only (model docstring display in admin)
install_scripts/        container entrypoint and default-script loader
backups/                not an app — README noting where `manage.py dbbackup` output lands
```

Third-party apps in `INSTALLED_APPS` (`mprov_control_center/settings.py`): `rest_framework`, `rest_framework_api_key`, `django_filters`, `jazzmin` (admin theme), `djangocodemirror` (script editor), `dbbackup`. `mprov_esxiprovisioner` is present in the tree but commented out of `INSTALLED_APPS` and not active. `django-cors-headers` is in `requirements.txt` but **not** wired into `INSTALLED_APPS`/`MIDDLEWARE` — CORS is not configured.

## URL routing map

Root urlconf is `mprov_control_center/urls.py`:

- `/` — `IndexAPIView`: unauthenticated HTML index of all endpoints.
- `/admin/` — jazzmin-themed Django admin.
- Direct [MProvView](api-foundation.md) routes (list at `x/`, detail at `x/<pk>/`): `networks/`, `networktypes/`, `systems/`, `systembmcs/`, `switches/`, `switchports/`, `systemgroups/`, `networkinterfaces/`.
- Special endpoints: `systems/register` (NADS registration), `ipxe/` (unauthenticated iPXE), `power/<action>/` (IPMI), `networks/<pk>/update-with-confirmation/` and `preview-subnet-changes/`, `datamodel/`, `/enroll/` (agent certificate enrollment/renewal and `ca.crt`, HTTPS-only — see [PKI & Agent Auth](../domain/pki-and-agent-auth.md)).
- `include()`-based route modules: `images/`, `systemimages/` (systems); `distros/`, `repos/`, `ostypes/`, `osrepos/` (osmanagement); `jobmodules/`, `jobservers/`, `jobs/`, `jobqueue/` (jobqueue); `scripts/`, `files/`, `ansibleplaybook/`, `ansiblerole/`, `ansiblecollection/` (scripts).
- Media files served via `static()` in the urlconf (script bodies live on disk under `MEDIA_ROOT`, see [Scripts](../domain/jobs-and-scripts.md#scripts)).

## Configuration

`settings.py` reads environment variables by name (values are never documented here): `SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS`, `SESSION_EXPIRE_SECONDS` (default 1800s via `django_session_timeout`), `TIME_ZONE` (or, if unset, `TZ` — `env_time_zone()` in `settings.py` strips a leading `:` and falls back to UTC with a warning when the value is a POSIX rule string rather than a zone name, so a compose stack that sets only `TZ` no longer runs in UTC (#456); `mprov_control_center/test_time_zone.py`), `MPROV_BACKUP_DIR` (see [Database and backups](#database-and-backups)), `DB_ENGINE`/`DB_NAME`/`DB_USER`/`DB_PASS`/`DB_HOST`/`DB_PORT` (default sqlite3), `TRUSTED_PROXIES` (see [API Foundation](api-foundation.md#api-version-lock)), the job-server housekeeping limits `JOBSERVER_FAIL_JOBS_AFTER_MINUTES` (default 10) and `JOBSERVER_DELETE_AFTER_DAYS` (default 0 = never, #254), the version-lock escapes `MPROV_SKIP_VERSION_CHECK` and `MPROV_VERSION_EXEMPT` (see [API Version Lock](api-foundation.md#api-version-lock)), and the LDAP group `LDAP_ENABLED`, `LDAP_URI`, `LDAP_BASE`, `LDAP_USER_DN_TEMPLATE`, `LDAP_ADMIN_GROUP`, `LDAP_SELF_SIGNED_CERT`, `LDAP_STAFF_GROUP`, `LDAP_SUPER_GROUP`. `env.example` additionally documents container-only vars consumed by `install_scripts/init_mpcc.sh` (`DJANGO_SUPERUSER_USERNAME`/`DJANGO_SUPERUSER_EMAIL`, optional `MPROV_SUPERUSER_PASSWORD`, `MPROV_MPCC_HOSTNAME`, `MPROV_MPCC_IPs`, `MPROV_DOMAINNAME`, `MPROV_DEVEL`) and the PKI/security vars `MPROV_TLS_DIR` (CA/TLS volume, default `/var/lib/mprov/tls`), optional site-cert `MPROV_TLS_CERT`/`MPROV_TLS_KEY`, `MPROV_SHARED_KEY_MODE` (`all`/`nodes`/`off` for the shared API key), and `MPROV_SIGNER_SOCKET` — see [PKI & Agent Auth](../domain/pki-and-agent-auth.md). `django-dotenv` loads a sibling `.env` from `wsgi.py`. Settings also define a minimal `LOGGING` config: `mprov.*` loggers (`mprov.provisioning`, `mprov.nads`, `mprov.serial`, `mprov.bmc`, `mprov.auth`) emit at INFO to stderr, which Apache forwards to the container log (#433, #485).

Auth options (client certificates, API keys, Basic/Session/Token, LDAP backend ordering) are detailed in [Authentication](api-foundation.md#authentication). With `LDAP_ENABLED=1`, settings no longer replaces `LOGGING` — `django_auth_ldap` is added at WARNING to the same stderr handler so the mPCC's own `mprov.*` log lines survive; `LDAP_DEBUG=1` adds DEBUG bind/group logging (#485, `mprov_control_center/test_ldap_logging.py`).

## Database and backups

- Default DB is sqlite at `BASE_DIR/db/db.sqlite3`; production containers set `DB_*` env vars (the compose stack ships its own database).
- Database-backed cache (`mprov_cache` table), `USE_TZ=True`.
- `django-dbbackup` writes to `/var/www/mprov_control_center/backups/` via `FileSystemStorage` (the `backups/` directory in the repo is just that README).
- `manage.py mprov_backup` / `manage.py mprov_restore` (added with #445, `utils/management/commands/`) are the standalone backup path: `dumpdata` writes one numbered fixture per app plus a `manifest.json` into a timestamped directory under `--output-dir` (default `MPROV_BACKUP_DIR`, i.e. `/var/lib/mprov/backups` — a root-only `VOLUME` in the image so backups survive an upgrade, #457), and restore loads **all** fixture files in a single `loaddata` call because the systems↔disklayouts M2M cycle has no linear app order (`utils/backup_apps.py`). The command refuses an output dir under `media/` or `static/` (resolved with `realpath`, since `db/` is a link to `media/`) and writes under umask 077 — a backup holds password hashes, API keys and BMC passwords (#457, `mprov_control_center/test_backup.py`). The README's upgrade flow still copies the archive out of the container, and the Apache config hard-denies backups left in `media/` by older versions (below). Installations upgrading from before 0.6.0 have no `mprov_backup` and must `mariadb-dump` from the `db` container instead; the README's Upgrading section also calls out copying `/etc/mprov` (secret key, admin password file, jobserver API key) and the `media/` directory out of the container (#465) — `media/` holds the script and uploaded files that the database only records by name, so a stack rebuilt from the database alone has no scripts.

## Web server serving and media hardening

Apache serves `media/` publicly because nodes and jobservers fetch scripts and files from it — always from a subdirectory (`<script type>/...`, `files/...`, see [Scripts](../domain/jobs-and-scripts.md#scripts)). But the default SQLite database is `media/db.sqlite3` (`db/` is a symlink to `media/`), so it was downloadable at `/media/db.sqlite3` (#457). `static/configs/mprov_control_center.conf` adds `LocationMatch` denies for any file at the top of `media/`, any `*.sqlite3` file, and any `mprov-backup-` directory; node fetches still work because they live in subdirectories. The patterns use `/+` because this httpd doesn't merge repeated slashes before matching. The shared CI test action starts the image and checks over HTTP that the database and a backup under `media/` get 403 while a script still gets 200, so future config edits can't silently re-open the exposure.

## Container bootstrap

`install_scripts/init_mpcc.sh` is the container entrypoint: run migrations, then on first start create the admin superuser, register the mPCC host, generate the jobserver API key, and import default scripts via `load_default_scripts.sh` from `default_scripts/` — the mprov_scripts commit that `install_scripts/mprov_scripts.ref` pins, fetched at image build time (overridable with `--build-arg MPROV_SCRIPTS_REF`) so every install of an image gets the same scripts and first start needs no network (#460; first start used to clone mprov_scripts master, so a released image's scripts changed day to day — `mprov_control_center/test_default_scripts.py`). Before Apache starts, the entrypoint runs as root: `manage.py mprov_tls --shell` creates the per-install CA and server cert in the `MPROV_TLS_DIR` volume and exports the cert paths for the Apache SSL config; starts the root-only signing helper (`python -m pki.signer`, the only reader of `ca.key`, on `MPROV_SIGNER_SOCKET`, killed with the container); and `manage.py mprov_enroll_token --bootstrap /etc/mprov/enroll_token` writes a first-start enrollment token (0600) so the local compose jobserver can enroll by certificate (#381 — see [PKI & Agent Auth](../domain/pki-and-agent-auth.md)). The superuser password is resolved by `install_scripts/superuser_password.sh` before it is consumed (#317): an operator-set `MPROV_SUPERUSER_PASSWORD` wins; otherwise a password saved by an earlier first run at `/etc/mprov/superuser_password` (root-only, mode 0600) is reused; otherwise a random one is generated, printed once to the container log, and saved only to that file — never baked in and never written to the world-readable `.env`. The user is then created with `create_superuser()` via `manage.py shell` (Django's `createsuperuser --noinput` only reads its own hardcoded env name). The jobserver key is created with `APIKey.objects.create_key()` inside `manage.py shell -c` and written from Python to `/etc/mprov/apikey` at mode 0600, so extraneous shell output can never leak into the file and the key is never briefly world-readable (#288). The entrypoint traps `TERM`/`INT` and forwards `SIGTERM` to the `setsid` process group running Apache, so `docker stop` shuts httpd down promptly instead of being killed after the timeout (#290). `MPROV_DEVEL=1` enables a dev mode that builds the venv and generates `.env` (secret key, superuser vars, `ALLOWED_HOSTS` harvested from interface addresses). The image is built by `Dockerfile`/`Containerfile` (identical) and published to `ghcr.io/mprov-ng/mprov-control-center`. The Dockerfile rewrites Apache's logging so every request on both ports is logged exactly once to stdout in combined format and no log files are written inside the container; the rewrite `grep`s its own seds so the build fails if a sed stops matching (#293). `static/configs/mprov_control_center.conf` deliberately has no `TransferLog` for this reason.

## CI

`.github/workflows/test-and-publish-dev.yml` runs on every PR and push to `main` (doc-only paths are ignored): build the image, then inside the container run `python manage.py check && python manage.py test`. The test suite includes a `MigrationsTest` that fails if a model change lacks a committed migration. The same test run is a reusable action (`.github/actions/mpcc-tests/`) that also gates the release-image workflow, so no image publishes untested (#333). Passing `main` pushes publish the `:dev` image, with workflow concurrency set so only the newest push publishes (#404). `.github/workflows/lint.yml` is a separate gate on PRs and `main`: `ruff check` (error rules in `ruff.toml`) plus `shellcheck -S error` over every tracked `.sh` file and `static/*.script` (#330). `.github/dependabot.yml` keeps GitHub Actions versions current, and `.github/workflows/openwiki-update.yml` regenerates this wiki daily.

## Change guidance

- Model change → always add a migration (CI enforces) and consider whether signals should queue [jobs](../domain/jobs-and-scripts.md).
- New API endpoint → subclass [MProvView](api-foundation.md), write the docstring (it becomes the rendered HTML docs page), and register the route in the app's `*_urls.py` or root urlconf.
- Admin changes → follow the per-app `admin.py` patterns (inlines, custom forms, confirm-view flows); use `common/admin.py` `AdminWizardModel` for multi-step creation wizards.

Key sources: `mprov_control_center/{settings,urls,views,wsgi}.py`, `install_scripts/`, `Dockerfile`, `.github/workflows/`, `env.example`.

ews,wsgi}.py`, `install_scripts/`, `Dockerfile`, `.github/workflows/`, `env.example`.

lows/`, `env.example`.


