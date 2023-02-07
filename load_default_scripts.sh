#!/bin/bash

# make a temp dir
# go into the temp dir
tempdir=`mktemp -d`
cd $tempdir

# checkout the scripts repo
git clone https://github.com/mprov-ng/mprov_scripts
if [ "$?" != "0" ]
then
    echo "Unable to checkout git."
    exit 1
fi
cd mprov_scripts/

# grab a list of files to copy and copy them to /var/www/mprov_control_center/media
scripts=`cat mpcc_scripts.yaml | grep "filename:" | awk '{print $2}'`
for i in $scripts
do
  type=`dirname $i`
  mkdir -p /var/www/mprov_control_center/media/$type
  /bin/cp -f $i /var/www/mprov_control_center/media/$type
  chown apache /var/www/mprov_control_center/media/${type}/$i
  
done
cd /var/www/mprov_control_center

# activate our venv
. bin/activate

# import the yaml as a fixture
python manage.py loaddata ${tempdir}/mprov_scripts/mpcc_scripts.yaml

cd /tmp
rm -rf $tempdir

