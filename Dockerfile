FROM rockylinux:8
ARG MPROV_INSTALL_OPTS ""
COPY install_scripts/install_mpcc.sh /tmp
RUN chmod 755 /tmp/install_mpcc.sh
RUN /tmp/install_mpcc.sh -d ${MPROV_INSTALL_OPTS}
ENTRYPOINT ["/var/www/mprov_control_center/install_scripts/init_mpcc.sh", "-d"]
EXPOSE 80
