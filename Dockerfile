# Start with Rocky Linux 8.8 as the base image
# Use the full URL to avoid confusion with podman builds.
FROM docker.io/rockylinux/rockylinux:8.8 

# Update system and install necessary dependencies
RUN dnf clean all && dnf update -y && \
    dnf install -y \
        curl \
        wget \
        vim \
        git \
        tar \
        unzip \
        gcc \
        make \
        python38 \
        python38-pip \
        openssh-server \
        openssl \
	ipmitool \
        jq \
        iproute \
        openldap-devel \
        dos2unix \
        httpd \
        mod_ssl \
        python38-devel \
	    mariadb \
	    mariadb-common \
	    mariadb-devel \
        python38-mod_wsgi.x86_64 && \
    dnf clean all

# Install EPEL and Development Tools
RUN dnf -y install epel-release && \
    dnf -y groupinstall "Development Tools" && \
    dnf clean all

# Configure Python 3.8 if necessary
RUN alternatives --set python3 /usr/bin/python3.8 || true && \
    dnf config-manager --enable powertools  && \
    dnf install -y parted-devel && \
    dnf clean all

# gen ssl
RUN openssl req -newkey rsa:2048 -nodes -keyout /etc/pki/tls/private/localhost.key -x509 -days 365 -out /etc/pki/tls/certs/localhost.crt -nodes -subj "/C=US/ST=Maryland/L=Baltimore/O=Johns Hopkins/OU=ARCH/CN=localhost"
RUN chown apache:apache /etc/pki/tls/private/localhost.key /etc/pki/tls/certs/localhost.crt

# Set up application environment
WORKDIR /var/www/

RUN mkdir -p mprov_control_center
COPY ./ /var/www/mprov_control_center

RUN cd mprov_control_center && \
    chmod 755 install_scripts/init_mpcc.sh && \
    python3 -m venv . && \
    . bin/activate && \
    pip3 install -r requirements.txt && \
    pip3 install mysqlclient

# grab a copy of memtest.
WORKDIR /var/www/mprov_control_center/static
RUN wget https://memtest.org/download/v7.20/mt86plus_7.20.binaries.zip && \
    unzip mt86plus_7.20.binaries.zip && \
    rm memtest32*

    
WORKDIR /var/www/mprov_control_center

# Prepare environment file
RUN echo "DJANGO_SUPERUSER_USERNAME=admin" > /var/www/mprov_control_center/.env && \
    echo "DJANGO_SUPERUSER_PASSWORD=admin" >> /var/www/mprov_control_center/.env && \
    echo "DJANGO_SUPERUSER_EMAIL=root@localhost" >> /var/www/mprov_control_center/.env 
    #echo "ALLOWED_HOSTS=$(hostname),127.0.0.1" >> /var/www/mprov_control_center/.env
    ## Create ENV VAR to set this outside of the container 

# Collect Static 
RUN . bin/activate && \
    python3 manage.py collectstatic --noinput

# Configure Apache for mProv Control Center
RUN wget -q -O static/busybox https://busybox.net/downloads/binaries/1.35.0-x86_64-linux-musl/busybox && \
    mkdir -p media && \
    ln -s media db && \
    chown apache media/ -R && \
    chmod u+sw media/ -R

# copy in the mprov_control_center apache config    
COPY static/configs/mprov_control_center.conf /etc/httpd/conf.d/mprov_control_center.conf

# change default logging to /dev/stdout
RUN sed -i 's/^ErrorLog.*$/ErrorLog \/dev\/stdout/' /etc/httpd/conf/httpd.conf
RUN sed -i 's/^CustomLog (.*) /CustomLog \/dev\/stdout/ ' /etc/httpd/conf/httpd.conf
RUN sed -i 's/^TransferLog.*$/TransferLog \/dev\/stdout/' /etc/httpd/conf/httpd.conf
RUN sed -i 's/^ErrorLog.*$/ErrorLog \/dev\/stdout/' /etc/httpd/conf.d/ssl.conf
RUN sed -i 's/^TransferLog.*$/TransferLog \/dev\/stdout/' /etc/httpd/conf.d/ssl.conf
RUN sed -i 's/^CustomLog (.*) /CustomLog \/dev\/stdout/ ' /etc/httpd/conf.d/ssl.conf
RUN echo 'LogFormat "%h %l %u %t \"%r\" %>s %b" common' > /etc/httpd/conf.d/containerlog.conf
RUN echo "CustomLog /dev/stdout common" >> /etc/httpd/conf.d/containerlog.conf
RUN rm -f /etc/httpd/logs /etc/httpd/run /etc/httpd/state
RUN mkdir -p /etc/httpd/logs /etc/httpd/run /etc/httpd/state
RUN chown apache:apache /etc/httpd/logs /etc/httpd/run /etc/httpd/state
RUN ln -s /dev/stdout /etc/httpd/logs/access_log
RUN ln -s /dev/stdout /etc/httpd/logs/error_log


COPY wait-for-it.sh /
RUN chmod 755 /wait-for-it.sh

# Expose HTTP port
EXPOSE 80
EXPOSE 443

# Run initialization script
CMD ["/var/www/mprov_control_center/install_scripts/init_mpcc.sh","-d"]
