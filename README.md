
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

The mPCC is a Django 4.2 application. It runs under Apache with `mod_wsgi` in a Rocky Linux 8 container image, `ghcr.io/mprov-ng/mprov-control-center`, and the container image is the only supported way to install it.

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
  ghcr.io/mprov-ng/mprov-control-center:latest
```

Keep these volumes:
- `/var/www/mprov_control_center/media` holds the SQLite database (if you use it), images and uploaded files.
- `/etc/mprov` holds the generated Django secret key, the admin password and the job server API key.
- `/var/lib/mprov/backups` holds the backups `mprov_backup` writes (see [Upgrading](#upgrading)). Only root can read it.

Port 443 is served with a self-signed certificate made when the image is built.

## Image tags
- `:vX.Y.Z` is a release, and `:latest` is the newest release.
- `:dev` is built from `main` after every merge, once the tests pass.

The mPCC, its job servers and mash must all run the same major.minor version (for example, all `0.6`). A client with the API key that sends another version, or none, gets `426 Upgrade Required` ([#452](https://github.com/mprov-ng/mprov_control_center/issues/452)), so upgrade them together.

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
- creates an API key for the job server and writes it to `/etc/mprov/apikey`. mprov-compose's job server shares the `/etc/mprov` volume and uses this key, so it registers with no further setup;
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
3. Upgrade job servers on other hosts, and mash, to the same major.minor version.
4. If you first installed before 0.6, change the `admin` password now. Older versions created `admin` with a fixed, published default password ([#337](https://github.com/mprov-ng/mprov_control_center/pull/337)), and upgrading doesn't change it.

# Bare-metal installs
The old bare-metal installer (`install_mpcc.sh`) has been removed and is no longer supported. It also set up an NFS-exported `/export/mprov` share, built Slurm into it, and installed MLX OFED, NVIDIA drivers and Ansible on the mPCC host. None of that is provided by the container image; if you need those, set them up separately.
