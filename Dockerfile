# Start with Rocky Linux 8.8 as the base image
# Use the full URL to avoid confusion with podman builds.
FROM docker.io/rockylinux/rockylinux:8.8 

# Set environment variables
ENV LANG=en_US.UTF-8 \
    LC_ALL=en_US.UTF-8

# Disable SELinux
RUN sed -i 's/^SELINUX=.*/SELINUX=disabled/' /etc/selinux/config && \
    setenforce 0 || true

# Update system and install necessary dependencies
RUN dnf update -y && \
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
        jq \
        iproute \
        openldap-devel \
        dos2unix \
        httpd \
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

# Set up application environment
WORKDIR /var/www/
RUN git clone https://github.com/mprov-ng/mprov_control_center.git && \
    cd mprov_control_center && \
    chmod 755 install_scripts/init_mpcc.sh && \
    python3 -m venv . && \
    . bin/activate && \
    pip3 install -r requirements.txt && \
    pip3 install mysqlclient
    
WORKDIR /var/www/mprov_control_center

# Prepare environment file
RUN export echo "DJANGO_SUPERUSER_USERNAME=admin" >> /var/www/mprov_control_center/.env && \
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
    
COPY static/mprov_control_center.conf /etc/httpd/conf.d/mprov_control_center.conf
COPY wait-for-it.sh /
RUN chmod 755 /wait-for-it.sh

# Expose HTTP port
EXPOSE 80

# Run initialization script
CMD ["/var/www/mprov_control_center/install_scripts/init_mpcc.sh","-d"]
