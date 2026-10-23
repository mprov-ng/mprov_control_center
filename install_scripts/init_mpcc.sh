#!/bin/bash
if [ "$MPROV_DEVEL" == "1" ]
then
       echo "Running in development mode"
       if [ ! -d /var/www/mprov_control_center/ ]
       then
              echo "Error: No development mount found!" >&2
              exit 1

       fi
       if [ ! -e /var/www/mprov_control_center/.dev.init ]
       then
              # re-run the install stuff because we are running in dev mode first time.
              cd /var/www/mprov_control_center
              # git clone https://github.com/mprov-ng/mprov_control_center.git
              # chmod 755 install_scripts/init_mpcc.sh
              python3 -m venv .
              . bin/activate
              pip install --upgrade pip
              pip install -r requirements.txt
              pip install mysqlclient 
              # TODO: All these entries should be checking if they exist first.
              # generates a secret from django's utils
              export SECRET_KEY=`python -c 'from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())'`
              echo "SECRET_KEY='$SECRET_KEY'" > .env

              echo "DJANGO_SUPERUSER_USERNAME=admin" >> .env
              echo "DJANGO_SUPERUSER_PASSWORD=admin" >> .env
              echo "DJANGO_SUPERUSER_EMAIL=root@localhost" >> .env
              ALLOWED_HOSTS=""
              for i in `ip addr | grep "inet " | awk '{print $2}' | awk -F/ '{print $1}'`
              do
                     ALLOWED_HOSTS="${i},${ALLOWED_HOSTS}"
              done
              MYHOST=`hostname`
              ALLOWED_HOSTS=${MYHOST},${ALLOWED_HOSTS}
              echo "ALLOWED_HOSTS=$ALLOWED_HOSTS" >> .env

              # other variables can be set directly in the ENV (for containers)
              # or via the .env file.   See the env.example for possible variables.
              
              # pull in a .env.custom if it exists.
              if [ -e .env.custom ]
              then 
                     cat .env.custom >> .env
              fi

              python manage.py collectstatic --noinput

              # grab a copy of busybox
              wget -q -O static/busybox https://busybox.net/downloads/binaries/1.35.0-x86_64-linux-musl/busybox

              touch /var/www/mprov_control_center/.dev.init

       fi
else
       echo "Running in production mode"
fi


cd /var/www/mprov_control_center
. bin/activate

python manage.py createcachetable
python manage.py migrate

# /etc/mprov/ holds the secret key and the jobserver API key.  Create it
# whichever way the secret key comes, as it may not be a mounted volume (#289).
mkdir -p /etc/mprov
chmod 700 /etc/mprov

# set up the secret key
# Use SECRET_KEY from the docker env if set, otherwise generate one once and
# keep it in /etc/mprov/ (a volume) so it survives restarts and image updates.
SECRET_KEY_FILE=/etc/mprov/secret_key
if [ -n "$SECRET_KEY" ]; then
    NEW_VALUE="$SECRET_KEY"
elif [ -s "$SECRET_KEY_FILE" ]; then
    NEW_VALUE=$(cat "$SECRET_KEY_FILE")
else
    NEW_VALUE=$(python3 -c 'from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())')
    echo "$NEW_VALUE" > "$SECRET_KEY_FILE"
    chmod 600 "$SECRET_KEY_FILE"
fi
case "$NEW_VALUE" in
    *\'*) echo "Error: SECRET_KEY must not contain a single quote" >&2; exit 1 ;;
esac
# delete and re-append rather than sed-replace, so key characters like & aren't interpreted.
sed -i '/^SECRET_KEY=/d' /var/www/mprov_control_center/.env
echo "SECRET_KEY='${NEW_VALUE}'" >> /var/www/mprov_control_center/.env

# let's adjust the env file based on the docker env
# only use the values that are set, so unset ones don't leave empty entries.
NEW_VALUE=""
for host in "$MPROV_MPCC_HOSTNAME" \
            "${MPROV_MPCC_HOSTNAME:+${MPROV_DOMAINNAME:+${MPROV_MPCC_HOSTNAME}.${MPROV_DOMAINNAME}}}" \
            "$MPROV_MPCC_IPs" \
            "$ALLOWED_HOSTS"
do
    if [ -n "$host" ]; then
        NEW_VALUE="${NEW_VALUE:+${NEW_VALUE},}${host}"
    fi
done

# if nothing is set, leave any existing ALLOWED_HOSTS in the .env alone.
if [ -n "$NEW_VALUE" ]; then
    if grep -q "^ALLOWED_HOSTS=" /var/www/mprov_control_center/.env; then
        # If it exists, update its value
        sed -i "s/^ALLOWED_HOSTS=.*/ALLOWED_HOSTS=${NEW_VALUE}/" /var/www/mprov_control_center/.env
    else
        # If it doesn't exist, append it to the file
        echo "ALLOWED_HOSTS=${NEW_VALUE}" >> /var/www/mprov_control_center/.env
    fi
fi
mkdir -p /var/www/mprov_control_center/db/
# First-run state comes from the database, not a marker file: the DB
# persists across container recreates, the container filesystem doesn't.
# Exit 0 = already initialized, 10 = needs init, anything else = error.
python manage.py shell -c "
import sys
from django.contrib.auth.models import User
sys.exit(0 if User.objects.filter(is_superuser=True).exists() else 10)
"
init_state=$?
if [ "$init_state" != "0" ] && [ "$init_state" != "10" ]
then
       echo "Error: unable to determine first-run state from the database, skipping first-run setup." >&2
fi
if [ "$init_state" == "10" ]
then
       python manage.py createsuperuser --noinput

       # systems.yaml refers to scripts that come from the mprov_scripts repo, so
       # it has to load after load_default_scripts.sh.  loaddata commits all its
       # fixtures together, so one missing reference rolls back every one of them.
       fixtures=()
       for f in */fixtures/*
       do
              [[ "$f" == systems/* ]] || fixtures+=("$f")
       done
       python manage.py loaddata "${fixtures[@]}"
       /var/www/mprov_control_center/install_scripts/load_default_scripts.sh
       # before the self System below, as the fixture rows have fixed pks.
       # Leave out any script that isn't loaded (e.g. the mprov_scripts clone
       # failed on an offline install), or the whole load fails.
       cat <<'EOF' | python manage.py shell
import glob, os, shutil, tempfile, yaml
from django.core.management import call_command
from scripts.models import Script

known = set(Script.objects.values_list("pk", flat=True))
tmpdir = tempfile.mkdtemp()
files = []
for path in sorted(glob.glob("systems/fixtures/*")):
    with open(path) as f:
        rows = yaml.safe_load(f) or []
    for row in rows:
        scripts = row.get("fields", {}).get("scripts")
        if scripts:
            missing = [s for s in scripts if s not in known]
            if missing:
                print(f"Warning: {row['model']} {row['pk']}: skipping scripts that aren't loaded: {', '.join(missing)}")
            row["fields"]["scripts"] = [s for s in scripts if s in known]
    out = os.path.join(tmpdir, os.path.basename(path))
    with open(out, "w") as f:
        yaml.safe_dump(rows, f)
    files.append(out)
call_command("loaddata", *files)
shutil.rmtree(tmpdir)
EOF

       # try to generate some interface commands based on ENV vars.
       IFACE_CMDS=""
       counter="0"
       OLD_IFS=$IFS
       IFS=","
       for ip in $MPROV_MPCC_IPs
       do
              counter=$((counter+1))
              IFACE_CMDS=$(
              cat <<-EOV 
$IFACE_CMDS
netinf = NetworkInterface.objects.create(hostname="${MPROV_MPCC_HOSTNAME}", name="eno$counter", system=selfSys, ipaddress="${ip}") 
netinf.save()
EOV
              )

       done

       IFS=$OLD_IFS

       # add our host to the mpcc
       . /var/www/mprov_control_center/bin/activate
       cat <<EOF | /var/www/mprov_control_center/manage.py shell
from systems.models import System, NetworkInterface
from django.contrib.auth.models import User

# get the admin user
user=User.objects.get(pk=1)

selfSys = System.objects.create(hostname="${MPROV_MPCC_HOSTNAME}", created_by=user,updated='1970-01-01T00:00+00:00',timestamp='1970-01-01T00:00+00:00')
selfSys.save()

${IFACE_CMDS}

EOF

       # generate an api key for the jobservers, and write it to /etc/mprov/apikey
       # from Python, so nothing else manage.py shell prints (a banner, or
       # newer Django's automatic-imports line) can end up in the file (#288).
       # The file is created 0600, so the key is never readable by others.
       python3 manage.py shell -c "
import os
from rest_framework_api_key.models import APIKey
_, key = APIKey.objects.create_key(name='mProv Jobserver Key')
fd = os.open('/etc/mprov/apikey', os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
with os.fdopen(fd, 'w') as f:
    f.write(f'export MPROV_APIKEY={key}\n')
"
fi

# fix the db perms... again...
chown apache db/ -R
chmod u+w db/ -R

# start apache in a new process group, filters out signals to the
# container, e.g. SIGWINCH.  The -d flag is still accepted
# (mprov-compose passes it) but is ignored; this is the only mode.
setsid --wait /usr/sbin/apachectl -D FOREGROUND &
child_pid=$!
trap "kill -SIGINT $child_pid" SIGINT
wait $child_pid
