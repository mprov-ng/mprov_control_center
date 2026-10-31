---
type: Reference
title: mProv Control Center Quickstart
description: Entry point for the mProv Control Center (mPCC) documentation — a Django 4.2 + DRF bare-metal provisioning control center with an admin UI and REST API. Covers what it is, how it is installed, and where to go next.
tags: [mprov, django, drf, provisioning, quickstart]
---

# mProv Control Center (mPCC)

mPCC is the brain of the mProv bare-metal provisioning stack. It manages the inventory and lifecycle of physical machines (systems, NICs, BMCs, networks, disk layouts, OS distros, scripts) and issues jobs to external jobservers that perform the actual PXE booting, imaging, DNS/DHCP, and script execution. It exposes:

- A **Django admin UI** (jazzmin-themed) at `/admin/` for operators.
- A **REST/CRUD JSON API** under paths like `/systems/`, `/networks/`, `/jobs/`, used remotely by jobservers and automation.
- **Self-documenting endpoints**: a non-JSON `GET` to most API views returns the endpoint's docstring rendered as HTML, and `GET /datamodel/?model=app.models.Model` returns the JSON field structure of any model.

Stack: Django (pinned `django>=4.2,<5` in `requirements.txt` pending the Rocky 9 move), Django REST Framework, `djangorestframework-api-key`, optional LDAP (`django-auth-ldap`), Apache + `mod_wsgi` in a container. See [Architecture Overview](architecture/overview.md) for the full map.

## Installation and first steps

mPCC is installed as part of the full mProv stack via [mprov-compose](https://github.com/mprov-ng/mprov-compose) (mPCC + database + a jobserver on one node with Docker). The old bare-metal installer was removed; the container entrypoint [install_scripts/init_mpcc.sh](../install_scripts/init_mpcc.sh) runs migrations, creates the admin superuser, registers the mPCC host, generates the jobserver API key, and loads default scripts on first start.

- Admin UI: `http://<FQDN-or-IP>/admin/`. If `MPROV_SUPERUSER_PASSWORD` is not set, the entrypoint generates a random password on first start, prints it once to the container log, and saves it to `/etc/mprov/superuser_password` (root-only) — see [Architecture Overview](architecture/overview.md#container-bootstrap).
- After install, create an API key in the admin and run a [jobserver](https://github.com/mprov-ng/mprov_jobserver) so queued jobs execute.
- Configuration is via environment variables (names documented in [Architecture Overview](architecture/overview.md#configuration)); `env.example` lists the container variables. Never commit real `.env` values.

## Where to go next

| Topic | Page |
|---|---|
| Project layout, routing, settings, bootstrap, CI | [Architecture Overview](architecture/overview.md) |
| The shared API base class, auth, `?detail`, `/datamodel/` | [API Foundation](architecture/api-foundation.md) |
| Systems, NICs, BMCs, provision flag / PXE Boot gating, images, networks, IPMI power | [Systems & Networking](domain/systems-and-networking.md) |
| Job queue, jobservers, scripts, Ansible content | [Jobs & Scripts](domain/jobs-and-scripts.md) |
| OS distros/repos, disk layouts and RAID | [OS & Disk Management](domain/os-and-disk-management.md) |

## How the pieces fit together

Every domain app below models its entities and then exposes them through [MProvView](architecture/api-foundation.md), the shared DRF base class. Write-side signals in [Systems & Networking](domain/systems-and-networking.md) and [OS & Disk Management](domain/os-and-disk-management.md) do not call external systems directly — they queue jobs that external jobservers poll out of the [Job Queue](domain/jobs-and-scripts.md).

## Testing and change guidance

CI (`.github/workflows/test-and-publish-dev.yml`) runs on every PR and push to `main`: it builds the shipping Docker image, then runs `python manage.py check && python manage.py test` inside it, against SQLite and again against MariaDB 10.11 (#385, see [CI](architecture/overview.md#ci)). A separate lint gate (`.github/workflows/lint.yml`) fails on ruff or ShellCheck errors (#330). The suite includes a `MigrationsTest`, so any model change without a committed migration fails CI. When changing an app, add or run app-local tests (e.g. `systems/test_detail_serializer.py`, `disklayouts/test_dtype_default.py`).

## Backlog

- `osmanagement/views_noauth.py` and `systems/views_noauth.py` unauthenticated surface: only the iPXE/register paths were summarized; audit the full no-auth attack surface in a later pass.
- `mprov_esxiprovisioner` app exists but is commented out of `INSTALLED_APPS`; undocumented by design until re-enabled.
- `REVIEW-2026-10.md` (root) is a large internal review checklist tracking many fixes now in GitHub issues; not mirrored here.
