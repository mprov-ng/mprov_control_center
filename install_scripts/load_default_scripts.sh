#!/bin/bash

# The default scripts are built into the image, from the mprov_scripts
# commit install_scripts/mprov_scripts.ref pins (#460).
scriptsdir=/var/www/mprov_control_center/default_scripts
if [ ! -f "$scriptsdir/mpcc_scripts.yaml" ]
then
    echo "No default scripts in $scriptsdir."
    exit 1
fi
cd "$scriptsdir"

# grab a list of files to copy and copy them to /var/www/mprov_control_center/media
scripts=`cat mpcc_scripts.yaml | grep "filename:" | awk '{print $2}'`
for i in $scripts
do
  type=`dirname $i`
  mkdir -p /var/www/mprov_control_center/media/$type
  /bin/cp -f $i /var/www/mprov_control_center/media/$type
  chown apache /var/www/mprov_control_center/media/$type
  
done
cd /var/www/mprov_control_center

# activate our venv
. bin/activate

# import the yaml as a fixture
python manage.py loaddata scripts/fixtures/*
python manage.py loaddata "$scriptsdir/mpcc_scripts.yaml"

