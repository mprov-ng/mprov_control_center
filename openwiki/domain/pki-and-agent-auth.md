---
type: Reference
title: PKI, Agent Certificate Auth, and Enrollment
description: The mProv Control Center pki app — a per-install certificate authority that issues the mPCC HTTPS cert and per-agent client certificates, mTLS authentication of jobservers and nodes replacing shared-API-key trust, permission scoping via MProvPermission/pki rules, and the token/nonce enrollment flow signed by a root-only helper.
tags: [mprov, pki, tls, mtls, security, enrollment, jobservers]
---

# PKI, Agent Certificate Auth, and Enrollment

Issue #381 gave every mPCC install its own certificate authority and moved machine-to-mPCC trust from "everyone shares one API key" to per-agent client certificates. The `pki` app (`pki/`, in `INSTALLED_APPS`) does four jobs: run a CA, issue TLS certs, authenticate agents by client certificate, and enroll new agents. It is the security foundation for [API Foundation](../architecture/api-foundation.md) — its `ClientCertAuthentication` and `MProvPermission` are now the DRF defaults.

## The CA and the mPCC's own TLS certificate

Each install creates an EC P-256 CA (10-year life) at first start; all key material lives in `MPROV_TLS_DIR` (default `/var/lib/mprov/tls`, its own Docker volume, like backups per #457): `ca.key` (mode 0600, root-only), `ca.crt`, `server.key`, `server.crt`. `pki/ca.py` `ensure_tls()` — invoked as root by the entrypoint via `manage.py mprov_tls` before Apache starts — creates/loads the CA (refusing to build over a half-destroyed one) and issues/renews the mPCC server cert (1 year, renewed at <30 days remaining or when SAN names change; SANs come from `MPROV_MPCC_HOSTNAME`, `MPROV_DOMAINNAME`, `MPROV_MPCC_IPs`). A site-supplied certificate via `MPROV_TLS_CERT`+`MPROV_TLS_KEY` is served as-is, but the CA is still created for client-cert verification. See [Container bootstrap](../architecture/overview.md#container-bootstrap).

## Signing is firewalled behind a root-only helper

The Django process (Apache user) never reads `ca.key`. `pki/signer.py` is a standalone signing helper — the only reader of the CA key — serving JSON over a Unix socket (`MPROV_SIGNER_SOCKET`, default `/run/mprov/signer.sock`, socket group `apache`). It enforces a hard `POLICY`: allowed kinds (`jobserver`/`system`/`build`), a name regex, maximum lifetimes (90 d / 30 d / 2 h), and logs every signature. Django reaches it through `pki/signer_client.py`; `pki/issue.py` `issue_credential()` signs via the socket (tests use an in-process `local_signer`). The entrypoint starts the signer and kills it with the container.

## Agent credentials and models (`pki/models.py`)

- **AgentCredential** — one issued client cert per jobserver or system. `kind` (`jobserver`/`system`) with FKs to `jobqueue.JobServer` / `systems.System` (CASCADE: deleting the agent revokes its certs), a FK to a dedicated service user (`mprov.js.<host_id>` / `mprov.sys.<pk>`, unusable password, no staff), unique hex `serial` and SHA-256 `fingerprint`, the PEM `certificate`, validity window, `revoked_at`, `last_seen`. A DB check constraint enforces exactly one agent target per row.
- **EnrollmentToken** — one-time jobserver token: stored as SHA-256 `token_hash` (shown once), `prefix`, `note`, `expires` (default 24 h), `used_at`, enrolled jobserver. `make()`/`redeem()` under `select_for_update`.
- **BootNonce** — one-time per-boot nonce bound to a system and its source `ipaddress`, 15-minute expiry; `issue()` drops prior unused nonces, `redeem()` burns the nonce and validates the address.

## How an agent authenticates (mTLS)

`static/configs/mprov_ssl_client.conf` is inserted into the Apache 443 vhost: `SSLVerifyClient optional` with `SSLCACertificateFile ${MPROV_TLS_CA}` and `+ExportCertData`, passing `SSL_CLIENT_VERIFY`/`SSL_CLIENT_CERT` to Django. `pki/authentication.py` `ClientCertAuthentication` (first in `DEFAULT_AUTHENTICATION_CLASSES`) accepts the cert only when Apache reports SUCCESS (or via `X-SSL-Client-Cert` from a `TRUSTED_PROXIES` peer), re-checks the cert chains to this CA, matches the fingerprint to an **active** `AgentCredential`, and — for system certs — requires the source IP to be one of the system's NIC addresses (same socket-peer rule as #319). Any request that presents a bad cert gets 401, never silent anonymous fallback. `request.user` becomes the service user and `request.auth` the credential; `common/request.py` `acting_user()` gives signals correct attribution (#381).

## What each agent may call: `MProvPermission` + `pki/rules.py`

`common/permissions.py` `MProvPermission` replaces `HasAPIKeyOrIsAuthenticated` as the DRF default permission and scopes requests by role per `pki/rules.py` — "each agent limited to what it needs":

- **SYSTEM_RULES** (node cert): `GET /`; its own `systems/?self` row and `?hostname=<itself>`; its own NICs (list/one, `PATCH` limited to `ipv6ll`); their networks; its own BMC rows (`PATCH` `mac`/`ipv6ll`); `POST /systems/?self` limited to `netboot`, `booted`, `serial` (see [Systems & Networking](../domain/systems-and-networking.md)); `POST /enroll/renew/`.
- **JOBSERVER_RULES**: `GET` everything except `power/` and `datamodel/`; `POST /jobservers/` for its own `host_id`; own heartbeats and job claims; `PATCH` own or unclaimed jobs; `POST /jobs/`; `?addjs` on its own listings; `hosted_by=[itself]` filters; `POST /ostypes/`; `POST /enroll/renew/`.
- Anything else → 403.

The shared API key still exists for admin/automation but is governed by `MPROV_SHARED_KEY_MODE` (`all`/`nodes`/`off`) — jobservers and nodes no longer need it once enrolled. Auth ordering details are in [Authentication](../architecture/api-foundation.md#authentication).

## Enrollment flow (`/enroll/`, HTTPS-only)

Routes in `pki/urls.py` mounted at `/enroll/` (`pki/views.py`):

- `POST /enroll/jobserver/` `{token, csr, host_id, name}` — redeems an `EnrollmentToken`, registers the jobserver by `host_id`, issues a 90-day cert. Tokens come from `manage.py mprov_enroll_token`; with `--bootstrap /etc/mprov/enroll_token` the entrypoint writes one (mode 0600) so the local compose jobserver can enroll on first start, and it is consumed only until the first enrollment. This replaces baking the shared key into the jobserver — see [Jobs & Scripts](../domain/jobs-and-scripts.md).
- `POST /enroll/system/` `{nonce, csr}` — the nonce is minted at boot time: the unauthenticated `/ipxe/` endpoint appends `mprov_enroll=<nonce> mprov_ca=<fingerprint>` to the install kernel cmdline (`enroll_params()` in `systems/views_noauth.py`, skipped for N.A.D.S. boots and when no CA exists), so only the node booting from that address on that boot can redeem it (15-min expiry). Issues a 30-day cert.
- `POST /enroll/renew/` — a current cert may renew within its last 30 days (jobserver) / 15 days (system); re-enrollment revokes the older credential. Signer down → 503.
- `GET /enroll/ca.crt` — the CA bundle, so agents can verify the mPCC.

Tests: `pki/test_ca.py`, `pki/test_models.py`, `pki/test_auth.py`, `pki/test_enroll.py`.

## Change guidance

- Adding an endpoint agents call: it is denied by default — add an explicit rule in `pki/rules.py` with a test in `pki/test_auth.py`; never widen `MProvPermission` itself.
- Anything touching cert issuance must go through `pki/issue.py`/the signer socket so `POLICY` lifetimes stay enforced; the Django app must never open `ca.key`.
- `pki` is in `utils/backup_apps.py`, so `mprov_backup` captures credentials; the CA key itself lives in the `MPROV_TLS_DIR` volume and must be copied out on upgrade like `/etc/mprov` (see [Database and backups](../architecture/overview.md#database-and-backups)).
- Key sources: `pki/{ca,issue,signer,signer_client,authentication,rules,views,models}.py`, `common/{permissions,request}.py`, `static/configs/mprov_ssl_client.conf`, `install_scripts/init_mpcc.sh`.
