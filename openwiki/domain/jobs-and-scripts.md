---
type: Reference
title: Jobs & Scripts
description: The mProv Control Center job queue (Job, JobModule, JobServer heartbeat registration, job polling API, live status polling) and the scripts app (Script content-on-disk storage, version handling, Ansible playbooks/roles/collections).
tags: [mprov, jobs, jobservers, scripts, ansible, api]
---

# Jobs & Scripts

The [job queue](../../jobqueue/) is mPCC's only mechanism for getting work done outside the database: every signal in [Systems & Networking](systems-and-networking.md) and [OS & Disk Management](os-and-disk-management.md) writes jobs here, and external jobservers poll them out over the API. The [scripts app](../../scripts/) stores the provisioning payload (shell scripts and Ansible content) that jobs reference.

## Job queue (`jobqueue/`)

Models (`jobqueue/models.py`):

- **Job** — a unit of work with a JSONField `params`, a `JobStatus` FK, and an assigned `JobServer`. Saving an image-update job adds `deps: repo-sync` so imaging waits for repo sync. `queue_job()` dedupes identical pending jobs, so repeated signal firings don't spam the queue.
- **JobModule** (slug PK job types), **JobStatus**, **JobServer** (registered runners).
- **JobServer** housekeeping lives in `save()`: servers whose heartbeat is older than 60s are deleted whenever a save lands on second `:00` — heartbeat freshness is the liveness model.

API (`jobqueue/views.py`, all via [MProvView](../architecture/api-foundation.md)):

- `GET /jobs/` supports `module` (single ID or JSON array), `jobserver`, `status`, and `params` — a JSON-object whose keys are matched against the job's params (non-object → 400). This is how jobservers claim work.
- `POST /jobservers/` is an update_or_create heartbeat/register endpoint returning `{"pk": N}`, authenticated by API key.
- `?detail` on these endpoints nests related objects 3 levels deep (documented in each view docstring; mechanism in [API Foundation](../architecture/api-foundation.md)).
- `/jobqueue/status-changes/` (`JobStatusChangesView`, staff-only) powers the live admin: the Job changelist auto-reloads (`jobqueue/static/admin/js/auto_reload.js`) and consumes cache-backed toast notifications raised from `jobqueue/signals.py`.

Admin note: add/change permission is gated on the request path containing `add`/`change`, so read-only API keys cannot mutate jobs.

## Scripts (`scripts/`)

Models (`scripts/models.py`): `Script` (slug PK, `version` BigIntegerField, `scriptType`, `dependsOn`, and either an uploaded `filename` or inline `content`), `File`, and Ansible content: `AnsiblePlaybook`, `AnsibleRole`, `AnsibleCollection` (galaxy/git URLs; execution ordering is collections → roles → playbooks).

**Content lives on disk, not in the DB**: `Script.save()` writes the body to `MEDIA_ROOT/<type>/<slug>-v<version>`, runs `dos2unix` on it, then blanks the `content` field; a post_delete receiver removes the file. `ScriptAdmin.get_form()` lazily re-populates the textarea from the file when an admin edits a script. Editor UX uses `djangocodemirror`.

**Version spinner fix**: the admin sets `formfield_overrides = {models.BigIntegerField: {'min_value': 1}}` on all five ModelAdmins (`scripts/admin.py`). Without it the version input's HTML `min` was `-2**63` and browser spinner arrows couldn't step; `scripts/test_version_widget.py` asserts `min == 1` on every admin form.

## Change guidance

- New job types: create a `JobModule` and enqueue via `queue_job()` from signals/views — don't invent side channels; jobservers only understand this queue.
- Changes to `/jobs/` filtering semantics affect every jobserver in the field; keep view docstrings (the rendered API docs) in sync.
- Touching `Script.save()`/`delete()`: verify file-on-disk round-trip (admin edit repopulation and post_delete cleanup) — this logic is easy to break silently because the DB column is intentionally empty after save.
- Key sources: `jobqueue/{models,views,signals,admin,urls}.py`, `scripts/{models,admin,views}.py`, `scripts/test_version_widget.py`.
