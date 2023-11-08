#!/bin/bash

# NOTE: This script MAY NOT yet be idempotent!!!

# TODO: test this script's idempotence.

# Detect if selinux is enabled, and die if it is.
selinuxStat=`getenforce`

if [ "$selinuxStat" == "Enforcing" ]
then
    echo "ERROR: Selinux enabled and enforcing.  This is likely to cause issues.  Not continuing."
    exit 1 
fi
if [ "$selinuxStat" != "Disabled" ]
then
    echo "WARN: Selinux enabled but is permissive.  This may still cause issues, but might still work.  You have been warned."
fi

# time for some arg parsing.
BUILD_DOCKER=0
MYSQL_BUILD=0
PGSQL_BUILD=0
SQLIT_BUILD=0
DEVEL=0
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
                -x) 
                        DEVEL=1
                        shift
                        ;;

                *)
                        echo "Error: Unknown arg $1"
                        exit 1
                        ;;
        esac
done

if [[ ! -e ./env.db  && (  "$MYSQL_BUILD" == "1"  || "$PGSQL_BUILD" == "1" ) ]]
then
        echo "You chose a DB backed instatllation but no env.db file found in the current directory.  "
        echo "I have created one for you, please edit it and re-run this installer."
        cat <<- EOFdb > env.db
#DB_ENGINE=django.db.backends.mysql
#DB_NAME=mprov
#DB_USER=mprov
#DB_PASS=mprov
#DB_HOST=127.0.0.1
#DB_PORT=3306

EOFdb
	if [ "$BUILD_DOCKER" != "1" ]
 	then
        	exit 1
	fi
fi

if [ "$PGSQL_BUILD" == "1" ] && [ "$MYSQL_BUILD" == "1" ]
then
    echo "Error: Please specify one or none of the database options (-m or -p or neither)"
    exit 1
fi

if [ "$PGSQL_BUILD" == "0" ] && [ "$MYSQL_BUILD" == "0" ]
then
        SQLIT_BUILD=1
fi
if [ "$PGSQL_BUILD" == 1 ] || [ "$MYSQL_BUILD" == "1" ]
then    
        echo "You have selected one of the authenticated database options.  If you have not yet"
        echo "set up the client for passwordless access via it's config file, you may be "
        echo "prompted for the user and password to log into the database as a root user."
        sleep 5
fi

extra_pkgs=""
if [ "$PGSQL_BUILD" == "1" ]
then
        extra_pkgs="postgresql libpq-devel libpq gcc python38-devel"
fi
if [ "$MYSQL_BUILD" == "1" ]
then
        extra_pkgs="mariadb mariadb-common mariadb-devel gcc python38-devel mariadb-server"
fi
. env.db




dnf -y install epel-release
dnf -y groupinstall "Development Tools"
dnf -y install python38-mod_wsgi.x86_64 jq git wget iproute openldap-devel python38-devel dos2unix $extra_pkgs
# why is this in a separate repo?!
dnf -y --enablerepo=powertools install parted-devel
if [ "$MYSQL_BUILD" == "1" ]
then
        systemctl enable --now mariadb
        cat << EOF | mysql -u root mysql
        create database $DB_NAME;
        CREATE USER '$DB_USER'@'localhost' IDENTIFIED BY '$DB_PASS';
        grant all on $DB_NAME.* to '$DB_USER'@'localhost';
        flush privileges;
EOF

fi

RUNDIR=`pwd`
cd /var/www/
if cd mprov_control_center
then 
        git checkout main
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

if [ "$DEVEL" == "0" ]
then
        # we want a release
        latest=`git for-each-ref --sort=taggerdate | grep tags | tail -n1 | awk '{print $3}'`
        git checkout $latest > /dev/null
        if [ "$?" != "0" ]
        then
                echo "Error: Unable to check out latest release.  Proceeding with main branch.  This could be bad."
        fi
fi

chmod 755 install_scripts/init_mpcc.sh
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

mkdir -p db/ media
chown apache db/ -R
chown apache media/ -R
chmod u+sw db/ -R
chmod u+sw media/ -R


# set up the apache stuff
cd /etc/httpd/conf.d/
cat << EOF > mprov_control_center.conf
WSGIDaemonProcess mprov.arch.jhu.edu processes=2 threads=15 lang='en_US.UTF-8' locale='en_US.UTF-8' python-home=/var/www/mprov_control_center/ python-path=/var/www/mprov_control_center/
WSGIScriptAlias / /var/www/mprov_control_center/mprov_control_center/wsgi.py  process-group=mprov.arch.jhu.edu application-group=%{GLOBAL}
WSGIPythonHome /var/www/mprov_control_center/
WSGIPythonPath /var/www/mprov_control_center/
WSGIProcessGroup mprov.arch.jhu.edu
WSGIPassAuthorization On
WSGIRestrictEmbedded On

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

# we need to up the workers.
<IfModule mpm_prefork_module>
      StartServers              10
      MinSpareServers           10
      MaxSpareServers           20
      ServerLimit               2000
      MaxRequestWorkers         1500
      MaxConnectionsPerChild    10000
</IfModule>
EOF

# Run the scripts from install_scripts/install.d/ in order
for i in `ls /var/www/mprov_control_center/install_scripts/install.d | sort -n`
do
       /var/www/mprov_control_center/install_scripts/install.d/$i
done

if [ "$BUILD_DOCKER" != "1" ]
then
        /var/www/mprov_control_center/install_scripts/init_mpcc.sh
        systemctl enable httpd
        systemctl restart httpd
	echo
	echo "Please remember!  You should open up port 80 or whatever port you want to run your webserver on to your firewall if you are running one."
	echo 
	echo -e "\tExample Commands:"
        echo -e "\tfirewall-cmd --zone=public --add-service=http --permanent"
        echo -e "\tfirewall-cmd --reload"
	echo
	echo
	echo "mProv also has issues running with selinux enabled.  You can run 'setenforce 0' for now to disable selinux, but still get auditing."
	echo
	echo "You should open /var/www/mprov_control_center/.env and add your hostname(s), IP(s) and FQDNs that you plan to use to access the mPCC"
	echo "If you don't, you may get a '400' error in the browser.  Make sure you 'touch /var/www/mprov_control_center/mprov_control_center/wsgi.py'"
	echo "after you edit the .env file to "restart" python wsgi."
	echo
	
fi
