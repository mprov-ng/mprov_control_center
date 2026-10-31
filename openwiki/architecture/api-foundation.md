---
type: Reference
title: mPCC API Foundation
description: How MProvView in common/views.py powers every mProv Control Center API endpoint — authentication (API keys, LDAP, sessions), the ?detail nested-detail serializer mechanism, query-param filtering, self-documenting endpoints, and the /datamodel/ introspection endpoint.
tags: [mprov, drf, api, authentication, serializers, datamodel]
---

# API Foundation

Nearly every JSON endpoint in mPCC subclasses `MProvView` (`common/views.py`), which combines DRF list/create/retrieve/update/destroy mixins with project-specific conventions. Understanding this one class explains most endpoint behavior across [Systems & Networking](../domain/systems-and-networking.md), [Jobs & Scripts](../domain/jobs-and-scripts.md), and [OS & Disk Management](../domain/os-and-disk-management.md).

## MProvView behavior

- **Permissions**: `HasAPIKeyOrIsAuthenticated` (`common/permissions.py`) — an `X-API-Key` header or any authenticated session/Basic/Token identity. The same class is the DRF `DEFAULT_PERMISSION_CLASSES` in settings, so non-`MProvView` API views get identical behavior; a plain tuple of the two permissions would have required both (#272).
- **Verbs**: `GET` list/retrieve, `POST` create, `PATCH` update, `DELETE` delete. `PUT` is explicitly rejected with `HttpResponseNotAllowed(["GET","POST","PATCH","DELETE"])`. `patch()`/`delete()` unpack `*args, **kwargs` into `partial_update`/`destroy` so the URL pk reaches the DRF mixins (this was a bug fixed recently — earlier versions dropped the kwargs). An API-key (anonymous session) `PATCH` records `created_by` as `admin`.
- **Query-param filtering**: `filter_by_query_params()` applies any `?FIELD=VALUE` exact match against model fields; invalid fields return a 400 body, and an empty result set returns 404. Unknown keys — including lookups like `?hostname__startswith=` — are errors, not silently ignored, so a typo'd filter can't return every row (#390). `?detail`, `?search` and `?format` are always accepted (`base_query_params`); a view lists its own accepted keys in `extra_query_params` (e.g. `SystemAPIView`: `self`), and views that filter themselves (e.g. `JobAPIView` for `module`/`params`/`jobserver`/`status`) apply the same check.
- **Self-documenting**: a non-JSON `GET` returns the view class docstring rendered as Markdown into a styled HTML page. Docstrings are therefore user-facing API docs — update them when endpoint behavior changes.
- **`created_by` auditing**: model signals sniff the current request by walking `inspect.stack()` for the middleware `get_response` frame (see `systems/models.py`), so admin/API attribution works without explicit plumbing.

## Detail reads: `?detail` and the detail serializer

A `GET` with a URL pk, or with `?detail`, sets a per-request `serve_detail` flag and swaps in the view's `detail_serializer_class` — or an auto-generated depth-3 subclass produced by the `lru_cache`d `depth3_serializer()` helper. Lists without `?detail`, and all writes, use the flat `serializer_class` (primary keys only).

This replaced an earlier design that mutated the shared serializer's `Meta.depth` at request time, which leaked nesting into subsequent flat requests and caused write failures (GitHub issues #266/#267; regression coverage in `systems/test_detail_serializer.py`). Endpoint docstrings on affected views now document `?detail` depth explicitly. When adding nested output to an endpoint, define a `detail_serializer_class` — never raise `Meta.depth`.

`SystemAPIView` is the main exception that manages its own `get()` and selects `SystemDetailSerializer` directly (`systems/views.py`).

## Authentication

Configured in `mprov_control_center/settings.py`:

- **API keys** (`rest_framework_api_key`): the machine-auth path used by jobservers and remote automation; the container entrypoint generates the jobserver key on first start.
- **Sessions / Basic / Token**: DRF defaults plus Django sessions for the admin UI. Session idle timeout via `django_session_timeout` (`SESSION_EXPIRE_SECONDS`, default 1800) redirects to `/admin/login/`.
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
ings}.py`.
