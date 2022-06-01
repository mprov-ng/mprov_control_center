#!/bin/bash

if [ "$1" == "-d" ]
then
  BUILD_DOCKER=1
fi

dnf -y install epel-release
dnf -y install python38-mod_wsgi.x86_64 ipmitool dnsmasq ipxe-bootimgs jq golang git 
cd /var/www/
GIT_SSH_COMMAND="ssh -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no" git clone git@github.com:mProv-Manager/mprov_control_center.git
if [ "$?" != "0" ]
then
    echo "Unable to checkout git."
    exit 1
fi



cd mprov_control_center
chmod 755 init_mpcc.sh
python3.8 -m venv .
. bin/activate
pip install -r requirements.txt

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
echo "ALLOWED_HOSTS=$ALLOWED_HOSTS" >> .env


# other variables can be set directly in the ENV (for containers)
# or via the .env file.   See the .env.example for possible varialbes.
python manage.py collectstatic --noinput

mkdir -p db/
chgrp apache db/ -R
chmod g+sw db/ -R


# set up the apache stuff
cd /etc/httpd/conf.d/
cat << EOF > mprov_control_center.conf
WSGIScriptAlias / /var/www/mprov_control_center/mprov_control_center/wsgi.py
WSGIPythonHome /var/www/mprov_control_center/
WSGIPythonPath /var/www/mprov_control_center/
WSGIDaemonProcess mprov.arch.jhu.edu processes=2 threads=15 lang='en_US.UTF-8' locale='en_US.UTF-8' python-home=/var/www/mprov_control_center/ python-path=/var/www/mprov_control_center/
WSGIProcessGroup mprov.arch.jhu.edu
WSGIPassAuthorization On

<Directory /var/www/mprov_control_center/mprov_control_center/>
        <Files wsgi.py>
                Require all granted
        </Files>
</Directory>

Alias /robots.txt /var/www/mprov_control_center/static/robots.txt
Alias /favicon.ico /var/www/mprov_control_center/static/favicon.ico

Alias /media/ /var/www/mprov_control_center/media/
Alias /static/ /var/www/mprov_control_center/static/

<Directory /var/www/mprov_control_center/static>
Require all granted
</Directory>

<Directory /var/www/mprov_control_center/media>
Require all granted
</Directory>

<Location "/secret">
    AuthType Basic
    AuthName "Top Secret"
    Require valid-user
    AuthBasicProvider wsgi
    WSGIAuthUserScript /var/www/mprov_control_center/mprov_control_center/wsgi.py
</Location>
EOF
if [ "$BUILD_DOCKER" != "1" ]
then
        /var/www/mprov_control_center/init_mpcc.sh
        systemctl enable httpd
        systemctl restart httpd
        firewall-cmd --zone=public --add-service=http
        firewall-cmd --zone=public --add-service=http --permanent
fi
