---
type: Reference
title: Jobs & Scripts
description: The mProv Control Center job queue (Job, JobModule, atomic job claiming, JobServer heartbeat registration with host IDs and per-network addresses, requeue/fail semantics, job polling API, live status polling) and the scripts app (Script content-on-disk storage, version handling, Ansible playbooks/roles/collections).
tags: [mprov, jobs, jobservers, scripts, ansible, api]
---

# Jobs & Scripts

The [job queue](../../jobqueue/) is mPCC's only mechanism for getting work done outside the database: every signal in [Systems & Networking](systems-and-networking.md) and [OS & Disk Management](os-and-disk-management.md) writes jobs here, and external jobservers poll them out over the API. The [scripts app](../../scripts/) stores the provisioning payload (shell scripts and Ansible content) that jobs reference.

## Job queue (`jobqueue/`)

Models (`jobqueue/models.py`):

- **Job** — a unit of work with a JSONField `params`, a `JobStatus` FK, and an assigned `JobServer`. Saving an image-update job adds `deps: repo-sync` so imaging waits for repo sync. `queue_job()` dedupes identical pending jobs, so repeated signal firings don't spam the queue. `requeue_job()` is the change-signal variant (#312): a pending job is left alone, a **running** job is never reset (resetting it made the same work run twice) — instead a separate pending job is queued so the change runs after it — and a finished job's row is reused, keeping one row per module+name under `select_for_update` (`jobqueue/test_job_requeue.py`). Pending jobs never carry a jobserver: setting a job back to pending clears it (migration `0017_pending_jobs_have_no_jobserver.py`, #296).
- **JobModule** (slug PK job types) and **JobStatus**.
- **JobServer** — registered runners, identified by a stable `host_id` when the job server sends one: registration then finds the row by `host_id`, so renaming a job server keeps its row and history, a name-only server is adopted, and a name clash with a different `host_id` is a 409 (mprov_jobserver#113, migration `0015_jobserver_host_id.py`, `jobqueue/test_jobserver_host_id.py`). `JobServerAddress` rows (migration `0016_jobserveraddress.py`) hold one address per network the server serves (mprov_jobserver#114); each heartbeat's `addresses` list replaces the last, and the unauthenticated `/images/` and repo redirects send a client to the address on the client's own network, falling back to the plain `address` (`JobServer.address_for()`, see [Systems & Networking](systems-and-networking.md)). Housekeeping lives in `save()`: servers whose heartbeat is older than 60s are deleted whenever a save lands on second `:00` — heartbeat freshness is the liveness model (the saving row itself is excluded). Naive heartbeat timestamps from clients are made timezone-aware on save instead of mislabeled with the wrong zone (#153, `jobqueue/test_heartbeat_timezone.py`). A `pre_delete` receiver **fails** the deleted server's RUNNING jobs to ERROR rather than re-queueing them — with no server, nothing would find them again, and a half-done image build or repo mirror may not be safe to rerun (#409, `jobqueue/test_job_requeue.py`).

API (`jobqueue/views.py`, all via [MProvView](../architecture/api-foundation.md)):

- `GET /jobs/` supports `module` (single ID or JSON array; a malformed array or empty value is a 400/empty result, never a 500 — #328), `jobserver`, `status`, and `params` — a JSON-object whose keys are matched against the job's params (non-object → 400). Param matching goes through `Job.filter_params()`: `JSON_CONTAINS` on MySQL/MariaDB, JSON key lookups elsewhere, because MariaDB leaves the right-hand side of a key lookup as a quoted JSON string and never matches string values (#385). Unknown query keys on this list GET are rejected like everywhere else (#390). Jobservers poll this for work; servers with the `job-claim` feature then atomically take a pending job via `POST /jobs/<id>/claim/` (below).
- `POST /jobservers/` is an update_or_create heartbeat/register endpoint returning `{"pk": N, "features": [...]}`, authenticated by API key. The `features` list (`FEATURES` in `jobqueue/views.py` — currently `addjs-version`, `host-id`, `jobserver-addresses`, `job-claim`) lets a job server detect what this mPCC supports and ignore names it doesn't know (#406). It validates `one_minute_load` (number), `port` (integer, string accepted), `jobmodules` (list), `host_id` (non-blank string ≤64 chars), and `addresses` up front and answers 400 instead of 500 on bad types (#328).
- `POST /jobs/<id>/claim/` (`JobClaimAPIView`, route in `jobqueue/jobs_urls.py`) claims a pending job for one job server atomically: a single conditional `UPDATE ... WHERE status=PENDING AND jobserver IS NULL` lets the database pick the winner, so exactly one of two racing servers gets 200 (job → RUNNING, `start_time` set); the loser and any non-pending job get 409 with the job's current status/jobserver; bad/unknown jobserver → 400, unknown job → 404 (#296, `jobqueue/test_job_claim.py`). Job servers use it when the register reply lists the `job-claim` feature; servers without it fall back to polling `GET /jobs/`.
- `?detail` on these endpoints nests related objects 3 levels deep (documented in each view docstring; mechanism in [API Foundation](../architecture/api-foundation.md)).
- `/jobqueue/status-changes/` (`JobStatusChangesView`, staff-only) powers the live admin: the Job changelist auto-reloads (`jobqueue/static/admin/js/auto_reload.js`) and consumes cache-backed toast notifications raised from `jobqueue/signals.py`. The toast poller (`jobqueue/static/admin/js/job_notifications.js`) stops polling on a 403 and redirects to `/admin/login/?next=...` instead of erroring forever after a session expiry (#255, `jobqueue/test_toast_script_visibility.py`).

Admin note: add/change permission is gated on the request path containing `add`/`change`, so read-only API keys cannot mutate jobs.

## Scripts (`scripts/`)

Models (`scripts/models.py`): `Script` (slug PK, `version` BigIntegerField, `scriptType`, `dependsOn`, and either an uploaded `filename` or inline `content`), `File`, and Ansible content: `AnsiblePlaybook`, `AnsibleRole`, `AnsibleCollection` (galaxy/git URLs; execution ordering is collections → roles → playbooks). `Script.scriptType` and `AnsiblePlaybook.scriptType` are `on_delete=PROTECT` (migration `0015_script_type_protect.py`): a type in use can't be deleted, and a script left typeless by an earlier `SET_NULL` deletion answers `save()`/PATCH with a ValidationError/400 asking for a type instead of crashing admin pickers with a 500 (#310, `scripts/test_script_type_protect.py`).

**Content lives on disk, not in the DB**: `Script.save()` writes the body to `MEDIA_ROOT/<type>/<slug>-v<version>`, runs `dos2unix` on it, then blanks the `content` field; a post_delete receiver removes the file. `ScriptAdmin.get_form()` lazily re-populates the textarea from the file when an admin edits a script. Editor UX uses `djangocodemirror`. `GET /scripts/files/<file-slug>/` (`FileDownloadView`) 302-redirects to the File's current versioned URL, so links into script payloads never need updating after a re-upload (#180, `scripts/test_file_download.py`).

**Version spinner fix**: the admin sets `formfield_overrides = {models.BigIntegerField: {'min_value': 1}}` on all five ModelAdmins (`scripts/admin.py`). Without it the version input's HTML `min` was `-2**63` and browser spinner arrows couldn't step; `scripts/test_version_widget.py` asserts `min == 1` on every admin form.

## Change guidance

- New job types: create a `JobModule` and enqueue via `queue_job()` from signals/views — don't invent side channels; jobservers only understand this queue.
- Changes to `/jobs/` filtering semantics affect every jobserver in the field; keep view docstrings (the rendered API docs) in sync.
- Touching `Script.save()`/`delete()`: verify file-on-disk round-trip (admin edit repopulation and post_delete cleanup) — this logic is easy to break silently because the DB column is intentionally empty after save.
- Key sources: `jobqueue/{models,views,signals,admin,urls}.py`, `scripts/{models,admin,views}.py`, `scripts/test_version_widget.py`.
