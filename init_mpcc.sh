#!/bin/bash
cd /var/www/mprov_control_center
. bin/activate

python ./manage.py migrate
python ./manage.py createsuperuser --noinput

python ./manage.py loaddata */fixtures/*

# fix the db perms... again...
chown apache db/ -R
chmod u+w db/ -R

# if we are running in docker, just start apache
if [ "$1" == "-d" ]
then
  /usr/sbin/apachectl -D FOREGROUND
fi