# Rocky Linux 9 with Python 3.12 from AppStream (#197).  Not pinned to a
# 9.x minor release: dnf update brings it to the latest 9.x anyway.
# Use the full URL to avoid confusion with podman builds.
FROM docker.io/rockylinux/rockylinux:9

# Update the system and install the dependencies in one layer, so the repo
# metadata is downloaded once and a slow mirror can only hit one step.
# fastestmirror picks a mirror by latency instead of taking the first one.
# The repos are enabled in the same order as before (base packages, then
# EPEL and Development Tools, then CRB, EL9's name for PowerTools, for
# parted-devel), so the same packages come from the same repos.
# The system python3 stays 3.9 (dnf needs it); the venv and mod_wsgi both
# use python3.12, so they must stay the same version.
# No curl package: the base image's curl-minimal conflicts with it, and
# already provides /usr/bin/curl for http and https.
# glibc-langpack-en: the en_US.UTF-8 locale mod_wsgi's daemon uses
# (static/configs/mprov_control_center.conf); EL9 packages it separately.
RUN echo "fastestmirror=True" >> /etc/dnf/dnf.conf && \
    dnf update -y && \
    dnf install -y \
        glibc-langpack-en \
        wget \
        vim \
        git \
        tar \
        unzip \
        gcc \
        make \
        pkgconf-pkg-config \
        python3.12 \
        python3.12-pip \
        python3.12-devel \
        python3.12-mod_wsgi \
        openssh-server \
        openssl \
        ipmitool \
        jq \
        iproute \
        openldap-devel \
        dos2unix \
        httpd \
        mod_ssl \
        mariadb \
        mariadb-common \
        mariadb-connector-c-devel && \
    dnf install -y epel-release && \
    dnf groupinstall -y "Development Tools" && \
    dnf config-manager --enable crb && \
    dnf install -y parted-devel && \
    dnf clean all

# Set up application environment
WORKDIR /var/www/

RUN mkdir -p mprov_control_center
COPY ./ /var/www/mprov_control_center

RUN cd mprov_control_center && \
    chmod 755 install_scripts/init_mpcc.sh && \
    python3.12 -m venv . && \
    . bin/activate && \
	pip install --upgrade pip && \
    pip3 install -r requirements.txt && \
    pip3 install "mysqlclient>=2.2.7,<3"

# The default scripts a fresh install loads, from the mprov_scripts commit
# install_scripts/mprov_scripts.ref pins (or --build-arg MPROV_SCRIPTS_REF),
# so every install of an image gets the same ones, and first start needs no
# network (#460).
ARG MPROV_SCRIPTS_REF
RUN ref="${MPROV_SCRIPTS_REF:-$(cat mprov_control_center/install_scripts/mprov_scripts.ref)}" && \
    git init -q mprov_control_center/default_scripts && \
    cd mprov_control_center/default_scripts && \
    git fetch -q --depth 1 https://github.com/mprov-ng/mprov_scripts "$ref" && \
    git checkout -q FETCH_HEAD && \
    git rev-parse HEAD > .ref && \
    rm -rf .git

# grab a copy of memtest.
WORKDIR /var/www/mprov_control_center/static
RUN wget https://memtest.org/download/v7.20/mt86plus_7.20.binaries.zip && \
    unzip mt86plus_7.20.binaries.zip && \
    rm memtest32*

    
WORKDIR /var/www/mprov_control_center

# Prepare environment file.  No MPROV_SUPERUSER_PASSWORD here (#317):
# the image must not ship default credentials; init_mpcc.sh generates a
# random password at first start and keeps it root-only in /etc/mprov.
RUN echo "DJANGO_SUPERUSER_USERNAME=admin" > /var/www/mprov_control_center/.env && \
    echo "DJANGO_SUPERUSER_EMAIL=root@localhost" >> /var/www/mprov_control_center/.env
    #echo "ALLOWED_HOSTS=$(hostname),127.0.0.1" >> /var/www/mprov_control_center/.env
    ## Create ENV VAR to set this outside of the container 

# Collect Static 
RUN . bin/activate && \
    python3 manage.py collectstatic --noinput

# Download busybox and set up the media and db directories
RUN wget -q -O static/busybox https://busybox.net/downloads/binaries/1.35.0-x86_64-linux-musl/busybox && \
    mkdir -p media && \
    ln -s media db && \
    chown apache media/ -R && \
    chmod u+sw media/ -R

# mprov_backup's default output directory: root-only, and a volume so
# backups survive the container being recreated, as an upgrade does (#457).
RUN install -d -m 700 /var/lib/mprov/backups
VOLUME /var/lib/mprov/backups

# The mPCC's own CA and HTTPS certificate (#381): made at first start by
# init_mpcc.sh (manage.py mprov_tls), never at build time, so each install
# has its own.  A volume, so they survive the container being recreated.
RUN install -d -m 755 /var/lib/mprov/tls
VOLUME /var/lib/mprov/tls

# copy in the mprov_control_center apache config    
COPY static/configs/mprov_control_center.conf /etc/httpd/conf.d/mprov_control_center.conf

# HTTPS (#381): ssl.conf serves the certificate init_mpcc.sh makes or the
# site supplies (MPROV_TLS_CERT/MPROV_TLS_KEY, which init_mpcc.sh exports),
# and asks for an optional client certificate from the mPCC's CA, which
# agents will authenticate with (static/configs/mprov_ssl_client.conf).
COPY static/configs/mprov_ssl_client.conf /tmp/mprov_ssl_client.conf

# Send all of Apache's logs to stdout, so docker logs has them, and log each
# request once, in the combined format, on both ports:
# - httpd.conf (port 80): the error log, and the indented access log
#   CustomLog, which is the only access log for the main server.
# - ssl.conf (port 443, its own vhost): the error log; the vhost's TransferLog
#   becomes the combined CustomLog, and its two-line ssl_request_log CustomLog,
#   which wrote to a file in the container, is removed.
RUN sed -i -e 's|^ErrorLog .*$|ErrorLog /dev/stdout|' \
        -e 's|^\( *\)CustomLog "logs/access_log" combined$|\1CustomLog /dev/stdout combined|' \
        /etc/httpd/conf/httpd.conf && \
    sed -i -e 's|^ErrorLog .*$|ErrorLog /dev/stdout|' \
        -e 's|^TransferLog .*$|CustomLog /dev/stdout combined|' \
        -e '/^CustomLog logs\/ssl_request_log \\$/,+1d' \
        -e 's|^SSLCertificateFile .*$|SSLCertificateFile ${MPROV_TLS_CERT}|' \
        -e 's|^SSLCertificateKeyFile .*$|SSLCertificateKeyFile ${MPROV_TLS_KEY}|' \
        -e '/^SSLCertificateKeyFile /r /tmp/mprov_ssl_client.conf' \
        /etc/httpd/conf.d/ssl.conf && \
    rm /tmp/mprov_ssl_client.conf && \
    grep -q '^ *CustomLog /dev/stdout combined$' /etc/httpd/conf/httpd.conf && \
    grep -q '^CustomLog /dev/stdout combined$' /etc/httpd/conf.d/ssl.conf && \
    ! grep -q 'ssl_request_log' /etc/httpd/conf.d/ssl.conf && \
    grep -q '^SSLCertificateFile ${MPROV_TLS_CERT}$' /etc/httpd/conf.d/ssl.conf && \
    grep -q '^SSLCertificateKeyFile ${MPROV_TLS_KEY}$' /etc/httpd/conf.d/ssl.conf && \
    grep -q '^SSLVerifyClient optional$' /etc/httpd/conf.d/ssl.conf
RUN rm -f /etc/httpd/logs /etc/httpd/run /etc/httpd/state
RUN mkdir -p /etc/httpd/logs /etc/httpd/run /etc/httpd/state
RUN chown apache:apache /etc/httpd/logs /etc/httpd/run /etc/httpd/state
RUN ln -s /dev/stdout /etc/httpd/logs/access_log
RUN ln -s /dev/stdout /etc/httpd/logs/error_log


COPY wait-for-it.sh /
RUN chmod 755 /wait-for-it.sh
RUN chown apache:apache /var/www/mprov_control_center/.env

# Expose HTTP port
EXPOSE 80
EXPOSE 443

# Run initialization script
CMD ["/var/www/mprov_control_center/install_scripts/init_mpcc.sh","-d"]
