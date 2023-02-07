#!/bin/bash
cd /var/www/mprov_control_center
. bin/activate

python ./manage.py migrate
python ./manage.py createsuperuser --noinput

# load the scripts before the fixtures.  Some fixtures
# may rely on the scripts being present

if [ -f ./load_default_scripts.sh ]
then
  # load the scripts fixture before loading the default scripts.
  python ./manage.py loaddata scripts/fixtures/*
  ./load_default_scripts.sh
fi

python ./manage.py loaddata */fixtures/*

# fix the db perms... again...
chown apache db/ -R
chmod u+w db/ -R

# if we are running in docker, just start apache
if [ "$1" == "-d" ]
then
  /usr/sbin/apachectl -D FOREGROUND
fi
