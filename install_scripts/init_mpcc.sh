#!/bin/bash
cd /var/www/mprov_control_center
. bin/activate


python manage.py migrate
python manage.py createsuperuser --noinput

python manage.py loaddata */fixtures/*

if [ "$1" != "-d" ] 
then
       # set up the secret key
       SECRET_KEY=$(python3 -c 'from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())') 
       echo "SECRET_KEY=$SECRET_KEY" >> /var/www/mprov_control_center/.env

       # Run the scripts from install_scripts/install.d/ in order
       for i in `ls /var/www/mprov_control_center/install_scripts/init.d | sort -n`
       do
              /var/www/mprov_control_center/install_scripts/init.d/$i
       done
else
       if [ ! -e /var/www/mprov_control_center/db/.initialized ]
       then
              # set up the secret key
              SECRET_KEY=$(python3 -c 'from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())') 
              echo "SECRET_KEY=$SECRET_KEY" >> /var/www/mprov_control_center/.env

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
