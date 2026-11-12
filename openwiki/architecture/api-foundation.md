---
type: Reference
title: mPCC API Foundation
description: How MProvView in common/views.py powers every mProv Control Center API endpoint — authentication (API keys, LDAP, sessions), the mProv-Version API version lock (426 Upgrade Required), the ?detail nested-detail serializer mechanism, query-param filtering, self-documenting endpoints, and the /datamodel/ introspection endpoint.
tags: [mprov, drf, api, authentication, serializers, datamodel]
---

# API Foundation

Nearly every JSON endpoint in mPCC subclasses `MProvView` (`common/views.py`), which combines DRF list/create/retrieve/update/destroy mixins with project-specific conventions. Understanding this one class explains most endpoint behavior across [Systems & Networking](../domain/systems-and-networking.md), [Jobs & Scripts](../domain/jobs-and-scripts.md), and [OS & Disk Management](../domain/os-and-disk-management.md).

## MProvView behavior

- **Permissions**: `MProvPermission` (`common/permissions.py`, DRF `DEFAULT_PERMISSION_CLASSES`) — replaced `HasAPIKeyOrIsAuthenticated` with the #381 agent-auth work: a client-cert agent gets only its kind's rules from `pki/rules.py`; an authenticated **person** (login, Basic, or API token) needs the matching Django model permission per view — superusers pass, everyone else gets `view`/`add`/`change`/`delete_<model>` checked by HTTP verb, and views that do more declare extra `mprov_permissions` (e.g. the power and network-confirmation views) or are superuser-only (#502); the shared API key is governed by `MPROV_SHARED_KEY_MODE`, which now **defaults to `off`** (`all` = accepted everywhere as before — deprecated in 0.7.0, removed in 0.8.0; `nodes` = only what a system may do, acting as the system whose NIC address the caller has; `off` = refused with a 403 naming the env var). See [PKI & Agent Auth](../domain/pki-and-agent-auth.md).
- **Verbs**: `GET` list/retrieve, `POST` create, `PATCH` update, `DELETE` delete. `PUT` is explicitly rejected with `HttpResponseNotAllowed(["GET","POST","PATCH","DELETE"])`. `patch()`/`delete()` unpack `*args, **kwargs` into `partial_update`/`destroy` so the URL pk reaches the DRF mixins (this was a bug fixed recently — earlier versions dropped the kwargs). An API-key (anonymous session) `PATCH` records `created_by` as `admin`.
- **Query-param filtering**: `filter_by_query_params()` applies any `?FIELD=VALUE` exact match against model fields; invalid fields return a 400 body, and an empty result set returns 404. Unknown keys — including lookups like `?hostname__startswith=` — are errors, not silently ignored, so a typo'd filter can't return every row (#390). `?detail`, `?search` and `?format` are always accepted (`base_query_params`); a view lists its own accepted keys in `extra_query_params` (e.g. `SystemAPIView`: `self`), and views that filter themselves (e.g. `JobAPIView` for `module`/`params`/`jobserver`/`status`) apply the same check.
- **Self-documenting**: a non-JSON `GET` returns the view class docstring rendered as Markdown into a styled HTML page. Docstrings are therefore user-facing API docs — update them when endpoint behavior changes.
- **`created_by`/`updated_by` auditing**: `common/request.py` `stamp_users()` sets `created_by` only when the instance is being created and `updated_by` on every save made during a request (`CurrentRequestMiddleware` thread-locals supply the request; saves outside a request change neither) — on `System`, `SystemImage`, and `Switch`, read-only in API/admin (#493, `systems/test_updated_by.py`).
- **Admin Site History of API writes**: `MProvView.perform_create/update/destroy` call `common/history.py` `record()`, which writes a Django `LogEntry` (field *names* only, never values) so API writes show up in the admin's object history like admin edits (#5). Attribution uses `acting_user()`: the person, an agent's cert-backed service user, service user `mprov.shared-key` for shared-key requests, and `mprov.nads` for N.A.D.S. registration; other unauthenticated writes fall back to the first superuser. `jobqueue` and `pki` are excluded (`NOT_RECORDED_APPS`); recording errors never fail the write. Related users render as plain IDs in `?detail` responses via `NoNestedUsersMixin` (`common/serializers.py`, #509, `common/test_no_nested_users.py`).

## Detail reads: `?detail` and the detail serializer

A `GET` with a URL pk, or with `?detail`, sets a per-request `serve_detail` flag and swaps in the view's `detail_serializer_class` — or an auto-generated depth-3 subclass produced by the `lru_cache`d `depth3_serializer()` helper. Lists without `?detail`, and all writes, use the flat `serializer_class` (primary keys only).

This replaced an earlier design that mutated the shared serializer's `Meta.depth` at request time, which leaked nesting into subsequent flat requests and caused write failures (GitHub issues #266/#267; regression coverage in `systems/test_detail_serializer.py`). Endpoint docstrings on affected views now document `?detail` depth explicitly. When adding nested output to an endpoint, define a `detail_serializer_class` — never raise `Meta.depth`.

Views that keep their own `get()` — `SystemAPIView` (`?powerstate`/`?hostname`/`?self`), `NetworkAPIView` (boolean `isdhcp`/`managedns` filters), `SystemBMCAPIView` (`?self`) — participate in the same mechanism by setting `serve_detail` and delegating to `self.retrieve()`, instead of each selecting a detail serializer by hand (#298, `common/test_view_detail_handling.py`). `JobAPIView` is the deliberate exception: a **single job fetched by pk stays flat** because mprov_jobserver's `update_job_status()` compares `status` as an ID; only `?detail` nests.

## API version lock

The mPCC, its jobservers, and mash must run the same major.minor version. `mprov_control_center/version.py` defines `__version__` and derives `API_VERSION` (major.minor only); `APIVersionMiddleware` (`common/version.py`, installed right after `SecurityMiddleware` in settings) enforces it (#452, `common/test_api_version.py`):

- **Every response** carries an `mProv-Version: <API_VERSION>` header — including 426s, 404s, and anonymous/browser replies. A jobserver's `startSession()` does `GET /` and treats a header-less reply as a mismatch, so `/` must always answer with the header even for exempt node IPs.
- **Only API-key (`Authorization: Api-Key`) requests are checked**: a missing, garbled, or different major.minor `mProv-Version` header → **426 Upgrade Required** with `{"detail", "expected", "got"}`. Matching forms (`0.6`, `0.6.1.dev0`) pass. Session/Basic auth is never checked.
- **Escape hatches** (`MPROV_SKIP_VERSION_CHECK=1` for dev/CI only; `MPROV_VERSION_EXEMPT` list of `path`/`path?querykey` entries with `<pk>` wildcards): an exempt endpoint passes a mismatched/missing version **only when the request comes from a known system's NIC address** (socket-peer identity per `TRUSTED_PROXIES`, same rule as #319), with a warning logged — this lets node scripts baked into older images keep working. Defaults cover `/`, `systems/?self|?hostname`, `systembmcs/?self|?system|<pk>/`, `networkinterfaces/?hostname|?system|<pk>/`, `networks/<pk>/` (see [Configuration](overview.md#configuration)).

## Authentication

Configured in `mprov_control_center/settings.py`:

- **Client certificates** (`pki.authentication.ClientCertAuthentication`, first in `DEFAULT_AUTHENTICATION_CLASSES`): the machine-auth path for enrolled jobservers and nodes over Apache mTLS; `request.user` is the agent's service user and `request.auth` its `AgentCredential`. See [PKI & Agent Auth](../domain/pki-and-agent-auth.md).
- **Per-user API tokens** (`authcustom.authentication.UserTokenAuthentication`, second; scheme `Authorization: Token <token>`, #502): `authcustom.models.UserToken` (an `AbstractAPIKey` subclass with `user` FK, `name`, `revoked`, `expiry_date`, throttled `last_used`), created three ways — the admin "API Tokens" page (staff see/revoke only their own unless granted the `authcustom` model permissions: `add_usertoken` lets privileged staff make a token for another active non-superuser staff user whose permissions are a subset of the maker's — checked in the dropdown queryset, `clean()`, and `save_model()` so it can't be a way to gain permissions; `view_usertoken`/`change_usertoken`/`delete_usertoken` see all / rename or bring forward an expiry (never push back or remove) and revoke / delete; the token's user is fixed at creation and nobody makes a token for a superuser, #561), `GET/POST/DELETE /tokens/` (`authcustom/views.py`; POST needs a password/session auth, never another token, and returns the secret once), or `manage.py mprov_token create|list|revoke`. Tokens are version-locked like API keys and enforced against the person's model permissions per the Permissions bullet above. `UserToken.created_by` (migration `0002_usertoken_created_by.py`) records who was shown the secret when that's a logged-in person; a token made by someone else whose user has since been promoted to superuser is refused at authentication (`authcustom/authentication.py`), while superusers' own tokens keep working. The old shared `APIKey` admin is re-registered as a legacy banner (`authcustom/apikey_admin.py`, #500).
- **API keys** (`rest_framework_api_key`): the deprecated shared key — accepted only when `MPROV_SHARED_KEY_MODE` is explicitly `all` or `nodes` (default `off`, #501); the container entrypoint no longer generates a jobserver key on first start since job servers enroll by certificate.
- **Sessions / Basic**: DRF defaults plus Django sessions for the admin UI. Session idle timeout via `django_session_timeout` (`SESSION_EXPIRE_SECONDS`, default 1800) redirects to `/admin/login/`.
- **LDAP**: enabled when `LDAP_ENABLED=1`. `django_auth_ldap` uses direct bind (`AUTH_LDAP_USER_DN_TEMPLATE`), gates access with `AUTH_LDAP_REQUIRE_GROUP`, maps staff/superuser from LDAP groups, and falls back to `ModelBackend`. `LDAP_SELF_SIGNED_CERT=1` bypasses TLS cert verification.
- CORS is **not** configured (`corsheaders` is installed as a package but absent from apps/middleware).

## `/datamodel/` introspection

`DataTypeView` (`mprov_control_center/views.py`, routed at `datamodel/`) lets clients discover request shapes:

- No params → JSON list of all project model class names.
- `?model=app.models.Model` (e.g. `jobqueue.models.Job`) → per-field JSON types via `MProvView.getJSONDataStructure()` and its `model_to_json_type_map`, plus the model's API `endpoint` when defined. Unknown model → 404.
- A field is marked `required` only when it is not blankable, has no default, and is editable — mirroring DRF `ModelSerializer` semantics, so clients are not told to send fields that have defaults (fixed in `common/views.py`; tests in `mprov_control_center/test_datamodel_type.py`).

## Change guidance

- Behavior changes in `MProvView` affect **every** endpoint — run the full `manage.py test` suite, not just one app.
- `common/testing.py` holds shared test helpers; recent regression tests (`systems/test_detail_serializer.py`, `common/test_foundation.py`) are the reference for base-class changes.
- Key sources: `common/views.py`, `common/serializers.py` (`NestedPrimaryKeyRelatedField`), `mprov_control_center/{views,urls,settings}.py`.
