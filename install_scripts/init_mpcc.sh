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

              # append the db stuff if a file exists.
              if [ -e "${RUNDIR}/env.db" ]
              then
                     cat ${RUNDIR}/env.db >> .env
              else
                     echo "No env.db, continuing with Sqlite"
              fi

              # other variables can be set directly in the ENV (for containers)
              # or via the .env file.   See the .env.example for possible varialbes.
              
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


python manage.py migrate

# set up the secret key
# Check if the variable exists in the .env file
NEW_VALUE=$(python3 -c 'from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())') 
if grep -q "^SECRET_KEY" /var/www/mprov_control_center/.env; then
    # If it exists, update its value
    sed -i "s/^SECRET_KEY=.*$/SECRET_KEY=${NEW_VALUE}/" /var/www/mprov_control_center/.env
else
    # If it doesn't exist, append it to the file
    echo "SECRET_KEY=${NEW_VALUE}" >> /var/www/mprov_control_center/.env
fi

# let's adjust the env file based on the docker env

NEW_VALUE="$MPROV_MPCC_HOSTNAME,${MPROV_MPCC_HOSTNAME}.${MPROV_DOMAINNAME},$MPROV_MPCC_IPs,${ALLOWED_HOSTS}"
if grep -q "^ALLOWED_HOSTS=" /var/www/mprov_control_center/.env; then
    # If it exists, update its value
    sed -i "s/^ALLOWED_HOSTS=.*/ALLOWED_HOSTS=${NEW_VALUE}/" /var/www/mprov_control_center/.env
else
    # If it doesn't exist, append it to the file
    echo "ALLOWED_HOSTS=${NEW_VALUE}" >> /var/www/mprov_control_center/.env
fi

if [ "$1" != "-d" ] 
then

       # Run the scripts from install_scripts/install.d/ in order
       for i in `ls /var/www/mprov_control_center/install_scripts/init.d | sort -n`
       do
              /var/www/mprov_control_center/install_scripts/init.d/$i
       done
else
       if [ ! -e /var/www/mprov_control_center/db/.initialized ]
       then
              python manage.py createsuperuser --noinput

              python manage.py loaddata */fixtures/*
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

# generate an api key
              cat << EOF > /tmp/genAPIKey.py
import rest_framework_api_key
apikey = rest_framework_api_key.models.APIKey()
key = rest_framework_api_key.models.APIKey.objects.assign_key(apikey)
apikey.name="mProv Jobserver Key"
apikey.save()
print(key)
EOF

              apikey=`cat /tmp/genAPIKey.py | python3 manage.py shell`

              # echo this out to a file in /etc/mprov/
              echo "export MPROV_APIKEY=$apikey" > /etc/mprov/apikey
              chmod 600 /etc/mprov/apikey

              /var/www/mprov_control_center/install_scripts/load_default_scripts.sh
              touch /var/www/mprov_control_center/db/.initialized
       fi
fi

# fix the db perms... again...
chown apache db/ -R
chmod u+w db/ -R

# if we are running in docker, just start apache
if [ "$1" == "-d" ]
then
  # start apache in a new PG, filters out signals to the
  # container, ie. SIGWINCH
  setsid --wait /usr/sbin/apachectl -D FOREGROUND &
  child_pid=$!
  trap "kill -SIGINT $child_pid" SIGINT
  wait $child_pid
fi
