#!/bin/bash
cd /var/www/mprov_control_center
. bin/activate


python manage.py migrate
python manage.py createsuperuser --noinput

python manage.py loaddata */fixtures/*
# set up the secret key
SECRET_KEY=$(python3 -c 'from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())') 
echo "SECRET_KEY=$SECRET_KEY" >> /var/www/mprov_control_center/.env

# let's adjust the env file based on the docker env
echo "ALLOWED_HOSTS=$ALLOWED_HOSTS,$MPROV_MPCC_HOSTNAME,${MPROV_MPCC_HOSTNAME}.${MPROV_DOMAINNAME},$MPROV_MPCC_IPs" >> /var/www/mprov_control_center/.env

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
  /usr/sbin/apachectl -D FOREGROUND
fi
