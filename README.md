
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

mprov-compose's `.env` sets `TZ`, but the mPCC itself only reads `TIME_ZONE` ([#456](https://github.com/mprov-ng/mprov_control_center/issues/456)). Add `TIME_ZONE=America/New_York` (or your zone) to `.env` as well, or the admin UI shows times in UTC.

## Running the image without compose
The image runs on its own with SQLite, which is enough to try the mPCC out locally. SQLite is only for a local trial: for a real site, or anything reachable by other hosts, point it at MariaDB with the `DB_*` variables (see [Configuration](#configuration)).

```
docker run -d --name mpcc \
  -p 80:80 -p 443:443 \
  -e MPROV_MPCC_HOSTNAME=mprov-mpcc \
  -e MPROV_MPCC_IPs=10.1.2.1 \
  -e TIME_ZONE=America/New_York \
  -v mpcc-media:/var/www/mprov_control_center/media \
  -v mprov-conf:/etc/mprov \
  ghcr.io/mprov-ng/mprov-control-center:latest
```

Keep both volumes:
- `/var/www/mprov_control_center/media` holds the SQLite database (if you use it), images and uploaded files.
- `/etc/mprov` holds the generated Django secret key, the admin password and the job server API key.

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
| `TIME_ZONE` | The mPCC's time zone. Default: `UTC`. |
| `SECRET_KEY` | Django's secret key. Optional: if it's unset, one is generated on first start and kept in `/etc/mprov/secret_key`. |
| `MPROV_SUPERUSER_PASSWORD` | The `admin` password to set on first start, instead of a random one. Only read while there's no superuser yet. |
| `JOBSERVER_FAIL_JOBS_AFTER_MINUTES` | Fail a job server's running jobs after it hasn't been heard from for this many minutes. `0` turns this off. Default: `10`. |
| `JOBSERVER_DELETE_AFTER_DAYS` | Delete a job server after this many days without a heartbeat. Default: `0`, never. |
| `SESSION_EXPIRE_SECONDS` | Log admin users out after this many idle seconds. Default: `1800`. |
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
- loads the default scripts from [mprov_scripts](https://github.com/mprov-ng/mprov_scripts) and the default data.

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
1. Back up the database, and copy the backup out of the container to the host:
   ```
   docker compose exec mpcc bash -c 'cd /var/www/mprov_control_center && . bin/activate && \
     python manage.py mprov_backup --output-dir /root/mprov-backups'
   docker compose cp mpcc:/root/mprov-backups ./mprov-backups
   ```
   Keep the copy somewhere safe: it contains user accounts, API keys and BMC credentials. Don't write backups under `media/`, which the web server serves ([#457](https://github.com/mprov-ng/mprov_control_center/issues/457)). The default output directory is inside the container and is lost on upgrade, so always copy the backup out. `mprov_restore` loads a backup back in.
2. Pull the new image and recreate the container: `docker compose pull && docker compose --env-file .env up -d`. Migrations run automatically when it starts.
3. Upgrade the job servers and mash to the same major.minor version at the same time; until you do, they get `426 Upgrade Required`.

# Bare-metal installs
The old bare-metal installer (`install_mpcc.sh`) has been removed and is no longer supported. It also set up an NFS-exported `/export/mprov` share, built Slurm into it, and installed MLX OFED, NVIDIA drivers and Ansible on the mPCC host. None of that is provided by the container image; if you need those, set them up separately.
