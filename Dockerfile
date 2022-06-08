FROM rockylinux:8
ARG MPROV_INSTALL_OPTS ""
COPY install_mpcc.sh /tmp
RUN chmod 755 /tmp/install_mpcc.sh
RUN /tmp/install_mpcc.sh -d ${MPROV_INSTALL_OPTS}
ENTRYPOINT ["/var/www/mprov_control_center/init_mpcc.sh", "-d"]
EXPOSE 80