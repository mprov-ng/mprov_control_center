#!/bin/bash

if [ "$DISABLE_SLURM" ]
then
  exit 0
fi

install_path=/opt/mprov/

# PRE_REQS: mlx-ofed, nvidia drivers, 

# TODO: check if the slurm binary(ies) exist and check the version?

slurmdl=/tmp/slurmdl
dlurl="https://download.schedmd.com/slurm"

getent passwd slurm > /dev/null
if [ "$?" != "0" ]
then  
  echo "Error: Unable to get 'slurm' user id.  Adding locally."
  useradd -d /export/mprov/var/slurm -u 450 slurm
fi

sudo -u slurm mkdir -p $slurmdl
cd $slurmdl

latest_file=$(curl --silent ${dlurl}/SHA1 | awk '{print $2}' | grep -v latest | grep -v "rc[0-9]\.t" | sort -t. -k1,1 -k2,2n -k3,3n | tail -n1)
latest_ver=$(echo $latest_file | sed 's/.tar.bz2//')
short_ver=$(echo $latest_ver | sed 's/slurm-//')
installed_ver=""

if [ -e $install_path/sbin/slurmd ]
then
  installed_ver=`$install_path/sbin/slurmd --version | tr ' ' '-'`
fi

if [[ "$installed_ver" == "$latest_ver" ]]; then
    printf "Already at latest slurm version (${latest_ver}).\n"
else
    echo "Installing Dependencies..."
    dnf -y --enablerepo=powertools install \
      pam-devel \
      munge munge-devel \
      json-c-devel \
      libyaml-devel \
      numactl-devel \
      libjwt-devel \
      http-parser-devel \
      hwloc-devel \
      hwloc \
      hwloc-plugins \
      pmix-devel \
      ucx-devel \
      lz4-devel \
      freeipmi \
      rrdtool \
      dbus-devel \
      gtk2-devel \
      man2html \
      readline-devel \
      libcurl-devel \
      lua-devel \
      cuda-*-11-7 \
      kmod-iser \
      kmod-isert \
      kmod-kernel-mft-mlnx \
      kmod-knem \
      kmod-mlnx-ofa_kernel \
      kmod-srp \
      hcoll \
      ibutils2 \
      infiniband-diags \
      infiniband-diags-compat \
      libibumad \
      libibverbs \
      libibverbs-utils \
      librdmacm \
      librdmacm-utils \
      mft \
      mlnx-ethtool \
      mlnx-iproute2 \
      mlnx-ofa_kernel \
      mlnx-ofa_kernel-devel \
      mlnx-ofed-basic \
      mstflint \
      ofed-scripts \
      python3-pyverbs \
      rdma-core \
      rdma-core-devel \
      sharp \
      ucx-cma \
      ucx-devel \
      ucx-ib \
      ucx-knem 

    printf "Downloading $latest_file to $slurmdl...\n"
    pushd $slurmdl
    sudo -u slurm wget -q $dlurl/$latest_file -O $latest_file
    sudo -u slurm tar -xf $latest_file
    cd $latest_ver

    sudo mkdir -p ${install_path}etc/slurm/$short_ver/pam_slurm
    sudo chown slurm ${install_path}etc/slurm/ -R
    sudo -u slurm ./configure --prefix=${install_path}/ --sysconfdir=${install_path}/etc/slurm --enable-salloc-kill-cmd --with-json --with-yaml --with-hwloc --with-munge --with-mysql_config=/usr/bin --with-hdf5=no --with-ucx --enable-pam --with-pam_dir=${install_path}etc/slurm/$short_ver/pam_slurm --with-pmix=/usr
    sudo -u slurm make -j 16
    sudo make install
    if [ "$?" == "0" ]
    then
      echo "$latest_ver" > /export/mprov/etc/slurm.version
    fi
fi