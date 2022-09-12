#!/bin/bash

# TODO: Detect if selinux is enabled, and die if it is.
selinuxStat=`getenforce`

if [ '$selinuxStat' == 'Enforcing' ]
then
    echo "ERROR: Selinux enabled and enforcing.  This is likely to cause issues.  Not continuing."
    exit 1
fi
if [ '$selinuxState' == 'Permissive' ]
then
    echo "WARN: Selinux enabled but is permissive.  This may still cause issues, but might still work.  You have been warned."
fi

# TODO: Display a summary of the config to the user.


# time for some arg parsing.
BUILD_DOCKER=0
MYSQL_BUILD=0
PGSQL_BUILD=0
SQLIT_BUILD=0
while [[ $# -gt 0 ]]
do
        case $1 in
                -d)
                        BUILD_DOCKER=1
                        shift
                        ;;
                -m)
                        MYSQL_BUILD=1
                        shift
                        ;;
                -p)
                        PGSQL_BUILD=1
                        shift
                        ;;

                *)
                        echo "Error: Unknown arg $1"
                        exit 1
                        ;;
        esac
done
  
if [ "$PGSQL_BUILD" == "1" ] && [ "$MYSQL_BUILD" == "1" ]
then
    echo "Error: Please specify one or none of the database options (-m or -p or neither)"
    exit 1
fi

if [ "$PGSQL_BUILD" == "0" ] && [ "$MYSQL_BUILD" == "0" ]
then
        SQLIT_BUILD=1
fi

extra_pkgs=""
if [ "$PGSQL_BUILD" == "1" ]
then
        extra_pkgs="postgresql libpq-devel libpq gcc python38-devel"
fi
if [ "$MYSQL_BUILD" == "1" ]
then
        extra_pkgs="mariadb mariadb-common mariadb-devel gcc python38-devel"
fi

dnf -y install epel-release
dnf -y install python38-mod_wsgi.x86_64 jq git wget iproute $extra_pkgs
# why is this in a separate repo?!
dnf --enable-repo=powertools install parted-devel
RUNDIR=`pwd`
cd /var/www/
if cd mprov_control_center
then 
        git pull
        if [ "$?" != "0" ]
        then
            echo "Unable to checkout git."
            exit 1
        fi 
else
        git clone https://github.com/mprov-ng/mprov_control_center.git
        if [ "$?" != "0" ]
        then
            echo "Unable to checkout git."
            exit 1
        fi
	cd mprov_control_center
fi


chmod 755 init_mpcc.sh
python3.8 -m venv .
. bin/activate
pip install -r requirements.txt

extra_pip=""
if [ "$PGSQL_BUILD" == "1" ]
then
        extra_pip="psycopg2"
fi
if [ "$MYSQL_BUILD" == "1" ]
then
        extra_pip="mysqlclient"
fi

if [ "$extra_pip" != "" ]
then
        pip install $extra_pip
fi


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

# append the db stuff if a file exists.
if [ -e "${RUNDIR}/env.db" ]
then
        cat ${RUNDIR}/env.db >> .env
fi


# other variables can be set directly in the ENV (for containers)
# or via the .env file.   See the .env.example for possible varialbes.
python manage.py collectstatic --noinput

# grab a copy of busybox
wget -q -O static/busybox https://busybox.net/downloads/binaries/1.35.0-x86_64-linux-musl/busybox 

mkdir -p db/ media
chown apache db/ -R
chown apache media/ -R
chmod u+sw db/ -R
chmod u+sw media/ -R


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
	echo "Please remember!  You should open up port 80 or whatever port you want to run your webserver on to your firewall if you are running one."
	echo 
	echo -e "\tExample Commands:"
        echo -e "\tfirewall-cmd --zone=public --add-service=http --permanent"
        echo -e "\tfirewall-cmd --reload"
	echo
	echo
	echo "mProv also has issues running with selinux enabled.  You can run 'setenforce 0' for now to disable selinux, but still get auditing."
fi
