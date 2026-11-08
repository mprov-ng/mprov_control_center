
# mProv Control Center
![Build Status](https://img.shields.io/github/actions/workflow/status/mprov-ng/mprov_control_center/test-and-publish-dev.yml?style=plastic)
![Latest Version](https://img.shields.io/github/v/tag/mprov-ng/mprov_control_center?style=plastic)
![License](https://img.shields.io/github/license/mprov-ng/mprov_control_center?style=plastic)

The mProv Control Center (mPCC) is the heart of everything that mProv manages. It is the brain that runs everything through a web interface, thus allowing for ease of use. mProv runs a REST/CRUD API for interfacing to the database and allowing remote access. 

The mPCC performs a wide range of jobs, permissions, and maintenance:
- Authentication
- Networking
- Issuing jobs to the mprov_jobservers
- An endpoint for serving files to nodes that require PXE booting 
- Running scripts on nodes after boot

The mPCC is a Django 5.2 application on Python 3.12. It runs under Apache with `mod_wsgi` in a Rocky Linux 9 container image, `ghcr.io/mprov-ng/mprov-control-center`, and the container image is the only supported way to install it.

# Installation

## With mprov-compose (recommended)
[mprov-compose](https://github.com/mprov-ng/mprov-compose) starts the whole mProv stack on a single node: the mPCC, its MariaDB database and a job server. Its README is the reference for the steps; in short:

```
git clone https://github.com/mprov-ng/mprov-compose.git
cd mprov-compose
cp stack.env.dist .env
# edit .env: set the database passwords, MPROV_MPCC_IPs and MPROV_DOMAINNAME
docker compose --env-file .env up -d
```

The first start migrates and loads a new database before the web server comes up, which takes a few minutes. Then log in at `http://<host>/admin/` (see [The admin password](#the-admin-password)).

The mPCC takes its time zone from `TIME_ZONE`, or if that isn't set, from mprov-compose's `TZ` ([#456](https://github.com/mprov-ng/mprov_control_center/issues/456)). Before 0.6.3 it read only `TIME_ZONE`, so on an older version add `TIME_ZONE=America/New_York` (or your zone) to `.env` as well, or the admin UI shows times in UTC.

## Running the image without compose
The image runs on its own with SQLite, which is enough to try the mPCC out locally. SQLite is only for a local trial: for a real site, or anything reachable by other hosts, point it at MariaDB with the `DB_*` variables (see [Configuration](#configuration)). On SQLite, a System Group of more than 999 systems can't be saved either: the admin checks the selected systems in one query, and the image's SQLite allows only 999 values in a query.

```
docker run -d --name mpcc \
  -p 80:80 -p 443:443 \
  -e MPROV_MPCC_HOSTNAME=mprov-mpcc \
  -e MPROV_MPCC_IPs=10.1.2.1 \
  -e TIME_ZONE=America/New_York \
  -v mpcc-media:/var/www/mprov_control_center/media \
  -v mprov-conf:/etc/mprov \
  -v mpcc-backups:/var/lib/mprov/backups \
  -v mpcc-tls:/var/lib/mprov/tls \
  ghcr.io/mprov-ng/mprov-control-center:latest
```

Keep these volumes:
- `/var/www/mprov_control_center/media` holds the SQLite database (if you use it), images and uploaded files.
- `/etc/mprov` holds the generated Django secret key, the admin password and the job server API key.
- `/var/lib/mprov/backups` holds the backups `mprov_backup` writes (see [Upgrading](#upgrading)). Only root can read it.
- `/var/lib/mprov/tls` holds this install's own certificate authority (CA) and HTTPS certificate (see [HTTPS](#https)). Losing it means a new CA.

## HTTPS
At first start the mPCC makes its own CA and an HTTPS certificate signed by it, in `/var/lib/mprov/tls` ([#381](https://github.com/mprov-ng/mprov_control_center/issues/381)). Each install gets its own, made at start, never at image build time.
- The certificate covers `MPROV_MPCC_HOSTNAME` (and `MPROV_MPCC_HOSTNAME.MPROV_DOMAINNAME`), the `MPROV_MPCC_IPs` addresses, `localhost` and `127.0.0.1`. It lasts a year. It's renewed at start when it has under 30 days left, or when those names or addresses change.
- To trust it, give clients `ca.crt` from that directory: `docker cp mpcc:/var/lib/mprov/tls/ca.crt .`
- To serve your own certificate instead, mount it and set `MPROV_TLS_CERT` and `MPROV_TLS_KEY` to the certificate and key files. The CA is still made, as later releases use it to issue the job servers' and nodes' own credentials.
- Port 443 also asks for an optional client certificate from that CA. Browsers, mash and plain HTTP aren't affected.
- Job servers and booted systems will each authenticate with their own client certificate from that CA ([#381](https://github.com/mprov-ng/mprov_control_center/issues/381)). A system's certificate reaches only what a node does to itself (its own row, network interfaces and BMC entries), and a job server's reads the inventory and writes only its own state.
- Agents get those certificates by enrolling over HTTPS. The CA's key is read only by a small signing helper that runs as root in the container; the web server asks it to sign.
  - A job server enrolls once with a one-time token (`POST /enroll/jobserver/`). Make one in the admin under Agent Identities → Job Server Enrollment Tokens, or with `manage.py mprov_enroll_token`. It's shown once, is single-use and lasts 24 hours by default. On start, the mPCC writes one to `/etc/mprov/enroll_token` for the job server in the same compose stack, until a job server has enrolled. It also copies its CA certificate (never the CA's key) to `/etc/mprov/ca.crt` on every start, so that job server can check the mPCC's HTTPS certificate before enrolling.
  - A booting system enrolls with a one-time nonce that `/ipxe/` adds to its kernel command line (`mprov_enroll=`), next to the CA's fingerprint (`mprov_ca=`).
  - Agents renew their own certificates near expiry (`POST /enroll/renew/`). Revoke one under Agent Identities → Agent Credentials; enrolling again, or reinstalling, also revokes the old one.
  - Node images check their certificate at boot and daily (`mprov_enroll.py renew`, installed by the image scripts) and renew it in its last two weeks. A system's page shows when its certificate expires.
  - A node whose certificate has expired anyway (it was off for weeks, say) can't renew. Select it under Systems (or its group under System Groups) and use **Let these systems re-enroll (1 hour)**: for the next hour it can get a new certificate once, from one of its own addresses (`POST /enroll/recover/`). The node does that on its next check or boot.
  - Enrollment (`/enroll/`) isn't version-locked, so a node's helper keeps working across mPCC upgrades.
- `MPROV_SHARED_KEY_MODE` sets where the old shared API key is still accepted: `off` (the default from 0.7.0), `nodes` (only for what a node does to itself, for node images not yet rebuilt) or `all` (everywhere, as before 0.7). `nodes` and `all` log a warning at start.
- **The shared API key is deprecated in 0.7.0 and removed in 0.8.0.** It works only while `MPROV_SHARED_KEY_MODE` is `all` or `nodes`, and the API Keys admin pages say so. Move job servers and nodes to their own credentials (enroll the job servers, and rebuild node images); until then, set `MPROV_SHARED_KEY_MODE=nodes` or `all`, and unset it afterwards. Adding a key in the admin still works in 0.7, so a site still on `all` can rotate it.
- People and their scripts (mash included) use **API tokens** instead of the shared key: `Authorization: Token <token>`. A token acts as its user. Tokens are for staff users: make one under Authentication and Authorization → API Tokens (it's shown once), with `POST /tokens/ {"name": "...", "days": 365}` and your password (Basic), or with `manage.py mprov_token create --user <u> --name <n>`. `days` is optional; without it a token doesn't expire. Revoke one on the same page, with `DELETE /tokens/<prefix>/`, or with `manage.py mprov_token revoke <prefix>`.
- **From 0.7.0 people get only their own Django model permissions through the API**, however they sign in (login, Basic or a token): reading needs the model's *view* permission, adding *add*, changing *change*, deleting *delete*. Power actions need *change* on systems, and *view* on BMCs. Superusers can do everything, as before. Before 0.7.0 any logged-in user could use the whole API, so **after upgrading, give non-superuser staff the permissions they need** (Authentication and Authorization → Users or Groups).
- If `/var/lib/mprov/tls` can't be set up (for example only one of `MPROV_TLS_CERT` and `MPROV_TLS_KEY` is set), the container stops with the reason in its log.

## Managed files

Upload a file under **Scripts → Files** and give it a **Destination in the Image** (for example `/etc/chrony.conf`), with its owner, group and mode. Then attach it to an OS distribution, a system group or a system image. Every image built from those gets the file:

- Files are placed **before** the image's image-generation scripts and Ansible run, so those can use them. A package a later script installs may replace a placed file: rpm keeps an existing `%config` file and saves its own copy as `.rpmnew`, but not every file is marked `%config`.
- Files from the distro, the groups and the image add up. If two of them have the same destination, the later layer's wins (image over groups over distro), and the image's **Rendered Config** tab shows the conflict.
- Tick **Jinja Template** to render the file for each image, with the image's merged Configuration Parameters as `params`, plus `image` and `distro`. For example, `server {{ params.ntp_server }} iburst`. An undefined name is an error, and the Rendered Config tab shows it before you build.
- Changing a file doesn't rebuild images by itself, as with scripts. The admin lists the images that need a rebuild.
- **Anything placed in an image can be read by anyone who can download the image. Never put passwords, keys or other secrets in a managed file.**

## Changing BMC credentials

Select systems (or system groups) and use **Set BMC credentials**. You can:

- **store** the user and password in the mPCC only, and change the BMCs yourself;
- **change** them on the BMCs: a job server on each BMC's network runs a `bmc-rotate` job, which needs the module in its `MPROV_MODS`. It uses Redfish, or IPMI where Redfish isn't available. The password is changed first, and the user only after a login with the new password works. The mPCC stores only credentials a job server has just logged in with;
- **check** that the stored credentials still work, changing nothing.

Follow progress under **BMC Credential Changes**. If a change can't be confirmed (for example, the job server lost touch with the mPCC after the BMC accepted it), it's marked *unconfirmed*: the old credentials stay stored, and **Find which credentials work** tries the old and new ones and stores whichever logs in. Job servers don't verify BMCs' HTTPS certificates unless `bmcCABundle` is set, and the report flags each change made without verification.

## Image tags
- `:vX.Y.Z` is a release, and `:latest` is the newest release.
- `:dev` is built from `main` after every merge, once the tests pass.

The mPCC, its job servers and mash must all run the same major.minor version (for example, all `0.6`). A client that authenticates as an agent (a client certificate, the API key, Basic or a token) and sends another version, or none, gets `426 Upgrade Required` ([#452](https://github.com/mprov-ng/mprov_control_center/issues/452)), so upgrade them together.

# Configuration
The mPCC is configured through environment variables: mprov-compose passes in its `.env`, or use `-e` with `docker run`. [`env.example`](env.example) has every variable, with comments. The ones you're most likely to need:

| Variable | What it does |
|---|---|
| `MPROV_MPCC_HOSTNAME`, `MPROV_MPCC_IPs`, `MPROV_DOMAINNAME` | The mPCC's hostname, the comma-separated IPs used to reach it, and its domain. All of them go into `ALLOWED_HOSTS`, and they make up the mPCC's own System entry on first start. |
| `ALLOWED_HOSTS` | Any other comma-separated hostnames or IPs the mPCC is reached by. `localhost` and `127.0.0.1` are always allowed. |
| `DB_ENGINE`, `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASS` | The database. Unset, it's SQLite, which is for a local trial only. For MariaDB, use `DB_ENGINE=django.db.backends.mysql`. |
| `TIME_ZONE` | The mPCC's time zone, as a name such as `America/New_York`. Default: `TZ`, else `UTC`. A value that isn't a zone name (such as a POSIX rule) is logged and `UTC` is used. |
| `SECRET_KEY` | Django's secret key. Optional: if it's unset, one is generated on first start and kept in `/etc/mprov/secret_key`. |
| `MPROV_SUPERUSER_PASSWORD` | The `admin` password to set on first start, instead of a random one. Only read while there's no superuser yet. |
| `JOBSERVER_FAIL_JOBS_AFTER_MINUTES` | Fail a job server's running jobs after it hasn't been heard from for this many minutes. `0` turns this off. Default: `10`. |
| `JOBSERVER_DELETE_AFTER_DAYS` | Delete a job server after this many days without a heartbeat. Default: `0`, never. |
| `MPROV_BACKUP_DIR` | Where `mprov_backup` writes by default. Default: `/var/lib/mprov/backups`, a volume in the image. |
| `SESSION_EXPIRE_SECONDS` | Log admin users out after this many idle seconds. Default: `1800`. |
| `DATA_UPLOAD_MAX_NUMBER_FIELDS` | The most fields an admin form may post. A System Group posts one per member system, so raise this if saving a very large group fails with `TooManyFieldsSent`. Default: `10000`. |
| `TRUSTED_PROXIES` | Reverse proxies whose `X-Forwarded-For` header is trusted for node requests. Unset: none are trusted. |
| `LDAP_ENABLED` and `LDAP_*` | LDAP login for the admin UI; see `env.example`. |
| `MPROV_SKIP_VERSION_CHECK` | `1` turns off the API version check. For development and CI only, never in production. |
| `MPROV_VERSION_EXEMPT` | The endpoints that node scripts baked into older images may call without a matching version. The defaults are in `mprov_control_center/settings.py`. |

# First start
On its first start against an empty database, the container's entrypoint (`install_scripts/init_mpcc.sh`):
- runs the database migrations (it does this on every start);
- generates a Django secret key, unless `SECRET_KEY` is set, and keeps it in `/etc/mprov/secret_key`;
- creates the `admin` superuser;
- creates the mPCC's own System entry from `MPROV_MPCC_HOSTNAME` and `MPROV_MPCC_IPs`;
- writes a one-time job server enrollment token to `/etc/mprov/enroll_token` (on every start, until a job server has enrolled). mprov-compose's job server shares the `/etc/mprov` volume and enrolls with it, so it registers with no further setup. From 0.7.0 no shared API key is made;
- loads the default scripts and the default data. The default scripts come from [mprov_scripts](https://github.com/mprov-ng/mprov_scripts) and are built into the image, from the commit that [`install_scripts/mprov_scripts.ref`](install_scripts/mprov_scripts.ref) pins, so every install of a release gets the same scripts and first start needs no network ([#460](https://github.com/mprov-ng/mprov_control_center/issues/460)). To ship newer default scripts, change that commit in a PR. Sites that are already installed keep their own scripts.

## The admin password
Unless `MPROV_SUPERUSER_PASSWORD` was set, the `admin` password is random. It's printed once to the container log and kept, readable only by root, in `/etc/mprov/superuser_password`:

```
docker compose exec mpcc cat /etc/mprov/superuser_password     # mprov-compose
docker exec mpcc cat /etc/mprov/superuser_password             # docker run
```

Change it in the admin UI once you've logged in.

# Post installation
The admin UI is at `http://<FQDN or IP>/admin/`.

Each extra job server, beyond the one mprov-compose starts, needs an API key: create one in the admin UI under API Keys, then follow the [mprov_jobserver README](https://github.com/mprov-ng/mprov_jobserver/blob/main/README.md). It must run the same major.minor version as the mPCC.

When creating an API key in the mPCC, you only need to specify a name for the API key, the expire times are only if your security protocols dictate the need for expiring keys.

# Upgrading
Upgrade the mPCC, its job servers and mash in the same window. They must run the same major.minor version, and anything older than the mPCC gets `426 Upgrade Required`. Don't upgrade the mPCC and leave its job server for later: in testing, an old job server facing a new mPCC hung, and wrote a broken dnsmasq config that stopped DHCP and PXE boot.

Before you start:
- Remove `MPROV_SKIP_VERSION_CHECK` from mprov-compose's `.env` if it's there. Compose passes `.env` to every container, so a setting meant for the job server also turns off the mPCC's version check.
- Choose the release. mprov-compose's `docker-compose.yml` uses `:dev` for the mPCC and `:latest` for the job server, so `docker compose pull` on its own doesn't give you a particular release. Set both `image:` lines to the same release tag, for example `ghcr.io/mprov-ng/mprov-control-center:v0.6.0` and `ghcr.io/mprov-ng/mprov-jobserver:v0.6.0`.

1. Back up the database, and copy the backup out of the container to the host.
   - On 0.6.0 or newer, use `mprov_backup`:
     ```
     docker compose exec mpcc bash -c 'cd /var/www/mprov_control_center && . bin/activate && \
       python manage.py mprov_backup --output-dir /var/lib/mprov/backups'
     docker compose cp mpcc:/var/lib/mprov/backups ./mprov-backups
     ```
     From 0.6.3, `/var/lib/mprov/backups` is the default and its own volume (`mpcc-backups`), so backups survive the upgrade. Before 0.6.3 it's inside the container and is lost on upgrade, so always copy the backup out. `mprov_backup` refuses to write under `media/` or `static/`, which the web server serves ([#457](https://github.com/mprov-ng/mprov_control_center/issues/457)). `mprov_restore` loads a backup back in.
   - Before 0.6.0 there's no `mprov_backup`. Dump the database from the `db` container instead:
     ```
     docker compose exec -T db sh -c 'mariadb-dump -u root -p"$MYSQL_ROOT_PASSWORD" \
       --single-transaction --databases "$MYSQL_DATABASE"' > mprov-db.sql
     ```
   - Also copy `/etc/mprov`: `docker compose cp mpcc:/etc/mprov ./mprov-conf`. It holds the Django secret key, the admin password file and the job server API key. An upgrade in place keeps it (it's the `mprov-conf` volume), but you need it to rebuild the stack from the backup.
   - And copy `media/`: `docker compose cp mpcc:/var/www/mprov_control_center/media ./mprov-media`. Neither backup above includes it, and it holds the script files and uploaded files; the database only records their names. An upgrade in place keeps it (it's the `mpcc-media` volume), but a stack rebuilt from the database alone has no scripts, so image builds and post-boot scripts fail. To put it back, copy it in and give it to the web server's user:
     ```
     docker compose cp ./mprov-media/. mpcc:/var/www/mprov_control_center/media/
     docker compose exec mpcc chown -R apache: /var/www/mprov_control_center/media
     ```

   Keep these copies somewhere safe: they contain user accounts, API keys and BMC credentials.
2. Pull the new images and recreate the containers: `docker compose pull && docker compose --env-file .env up -d`. Migrations run automatically when the mPCC starts. If you also updated mprov-compose itself, the `db` container may be recreated too, which is a short, expected outage.
   - If the database was first created by an older release, some of its tables may still be in an older character set (`latin1`). Before the migrations run, the mPCC converts every such table, and the database's default, to the database's `utf8mb4` collation, keeping their data and foreign keys: new foreign keys to their text keys can't be created otherwise. It's done once, and on a large database it can make that first start take several minutes, so take the backup in step 1 first. If two values in a unique column would become duplicates under the new collation (for example `a` and `ä`), it stops before changing anything and names the table: make them distinct and restart the container. Development images from before this conversion existed could stop part way through the migrations with `errno: 150 "Foreign key constraint is incorrectly formed"`, leaving tables half created. If yours did, restore the backup from step 1 into an empty database before starting the new release: starting it on the half-migrated database fails with `Table ... already exists`.
3. Upgrade job servers on other hosts, and mash, to the same major.minor version.
   - **From 0.7.0 the shared API key is refused by default** (`MPROV_SHARED_KEY_MODE=off`), and 0.8.0 removes it (see [HTTPS](#https)). After upgrading, until you've moved them to their own credentials:
     - a job server that hasn't enrolled can't reach the mPCC. Enroll it with a token from Agent Identities → Job Server Enrollment Tokens (mprov-compose's own job server enrolls by itself), or set `MPROV_SHARED_KEY_MODE=all` meanwhile;
     - nodes booted from images built before 0.7.0 still use the key in their post-boot scripts. Rebuild the images, or set `MPROV_SHARED_KEY_MODE=nodes` meanwhile, which accepts the key only for what a node does to itself.
     Unset `MPROV_SHARED_KEY_MODE` once that's done.
   - Upgrading to 0.7.0 replaces the HTTPS certificate on port 443 with one from the install's own CA (see [HTTPS](#https)), and the container needs the new `/var/lib/mprov/tls` volume (`mpcc-tls` in mprov-compose). Any client that pinned the old certificate (a job server's `caBundle`, mash, scripts) needs `ca.crt` instead.
4. If you first installed before 0.6, change the `admin` password now. Older versions created `admin` with a fixed, published default password ([#337](https://github.com/mprov-ng/mprov_control_center/pull/337)), and upgrading doesn't change it.

# Bare-metal installs
The old bare-metal installer (`install_mpcc.sh`) has been removed and is no longer supported. It also set up an NFS-exported `/export/mprov` share, built Slurm into it, and installed MLX OFED, NVIDIA drivers and Ansible on the mPCC host. None of that is provided by the container image; if you need those, set them up separately.
