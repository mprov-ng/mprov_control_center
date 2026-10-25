---
type: Reference
title: mPCC Architecture Overview
description: Project layout, installed Django apps, URL routing map, environment configuration, container bootstrap, database and backup setup, and CI pipeline for the mProv Control Center repository.
tags: [mprov, django, architecture, routing, settings, ci, containers]
---

# Architecture Overview

mProv Control Center is a single Django project (`mprov_control_center/`, pinned `django>=4.2,<5` in `requirements.txt` until the Rocky 9 move, issue #197) that combines an operator admin UI with a DRF JSON API. Almost all API behavior flows through one shared base class, [MProvView](api-foundation.md), and almost all external side effects flow through the [job queue](../domain/jobs-and-scripts.md) rather than direct calls.

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
- Special endpoints: `systems/register` (NADS registration), `ipxe/` (unauthenticated iPXE), `power/<action>/` (IPMI), `networks/<pk>/update-with-confirmation/` and `preview-subnet-changes/`, `datamodel/`.
- `include()`-based route modules: `images/`, `systemimages/` (systems); `distros/`, `repos/`, `ostypes/`, `osrepos/` (osmanagement); `jobmodules/`, `jobservers/`, `jobs/`, `jobqueue/` (jobqueue); `scripts/`, `files/`, `ansibleplaybook/`, `ansiblerole/`, `ansiblecollection/` (scripts).
- Media files served via `static()` in the urlconf (script bodies live on disk under `MEDIA_ROOT`, see [Scripts](../domain/jobs-and-scripts.md#scripts)).

## Configuration

`settings.py` reads environment variables by name (values are never documented here): `SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS`, `SESSION_EXPIRE_SECONDS` (default 1800s via `django_session_timeout`), `TIME_ZONE`, `DB_ENGINE`/`DB_NAME`/`DB_USER`/`DB_PASS`/`DB_HOST`/`DB_PORT` (default sqlite3), and the LDAP group `LDAP_ENABLED`, `LDAP_URI`, `LDAP_BASE`, `LDAP_USER_DN_TEMPLATE`, `LDAP_ADMIN_GROUP`, `LDAP_SELF_SIGNED_CERT`, `LDAP_STAFF_GROUP`, `LDAP_SUPER_GROUP`. `env.example` additionally documents container-only vars consumed by `install_scripts/init_mpcc.sh` (`DJANGO_SUPERUSER_*`, `MPROV_MPCC_HOSTNAME`, `MPROV_MPCC_IPs`, `MPROV_DOMAINNAME`, `MPROV_DEVEL`). `django-dotenv` loads a sibling `.env` from `wsgi.py`.

Auth options (API keys, Basic/Session/Token, LDAP backend ordering) are detailed in [Authentication](api-foundation.md#authentication).

## Database and backups

- Default DB is sqlite at `BASE_DIR/db/db.sqlite3`; production containers set `DB_*` env vars (the compose stack ships its own database).
- Database-backed cache (`mprov_cache` table), `USE_TZ=True`.
- `django-dbbackup` writes to `/var/www/mprov_control_center/backups/` via `FileSystemStorage` (the `backups/` directory in the repo is just that README).

## Container bootstrap

`install_scripts/init_mpcc.sh` is the container entrypoint: run migrations, and on first start create the admin superuser, register the mPCC host, generate the jobserver API key, and import default scripts from the mprov_scripts repo via `load_default_scripts.sh`. The jobserver key is created with `APIKey.objects.create_key()` inside `manage.py shell -c` and written from Python to `/etc/mprov/apikey` at mode 0600, so extraneous shell output can never leak into the file and the key is never briefly world-readable (#288). The entrypoint traps `TERM`/`INT` and forwards `SIGTERM` to the `setsid` process group running Apache, so `docker stop` shuts httpd down promptly instead of being killed after the timeout (#290). `MPROV_DEVEL=1` enables a dev mode that builds the venv and generates `.env` (secret key, superuser vars, `ALLOWED_HOSTS` harvested from interface addresses). The image is built by `Dockerfile`/`Containerfile` (identical) and published to `ghcr.io/mprov-ng/mprov-control-center`. The Dockerfile rewrites Apache's logging so every request on both ports is logged exactly once to stdout in combined format and no log files are written inside the container; the rewrite `grep`s its own seds so the build fails if a sed stops matching (#293). `static/configs/mprov_control_center.conf` deliberately has no `TransferLog` for this reason.

## CI

`.github/workflows/test-and-publish-dev.yml` runs on every PR and push to `main` (doc-only paths are ignored): build the image, then inside the container run `python manage.py check && python manage.py test`. The test suite includes a `MigrationsTest` that fails if a model change lacks a committed migration. Passing `main` pushes publish the `:dev` image. `.github/dependabot.yml` keeps GitHub Actions versions current, and `.github/workflows/openwiki-update.yml` regenerates this wiki daily.

## Change guidance

- Model change → always add a migration (CI enforces) and consider whether signals should queue [jobs](../domain/jobs-and-scripts.md).
- New API endpoint → subclass [MProvView](api-foundation.md), write the docstring (it becomes the rendered HTML docs page), and register the route in the app's `*_urls.py` or root urlconf.
- Admin changes → follow the per-app `admin.py` patterns (inlines, custom forms, confirm-view flows); use `common/admin.py` `AdminWizardModel` for multi-step creation wizards.

Key sources: `mprov_control_center/{settings,urls,views,wsgi}.py`, `install_scripts/`, `Dockerfile`, `.github/workflows/`, `env.example`.
