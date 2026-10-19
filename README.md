
# mProv Control Center
![Build Status](https://img.shields.io/github/actions/workflow/status/mprov-ng/mprov_control_center/test-and-publish-dev.yml?style=plastic)
![Latest Version](https://img.shields.io/github/v/tag/mprov-ng/mprov_control_center?style=plastic)
![License](https://img.shields.io/github/license/mprov-ng/mprov_control_center?style=plastic)

The mProv Control Center (mPCC) is the heart of everything that mProv manages. It is the brain that runs everything through a web interface, thus allowing for ease of use. mProv runs a REST/CRUD API for interfacing to the database and allowing remote access. 

The mPCC performs a wide range of jobs, permissions, and maintenance:
- Authentication
- Networking
- Issuing jobs to the mprov_jobservers
- An endpoint for serving files to nodes that require PXE booting 
- Running scripts on nodes after boot

The mPCC is based on Django 3.2 and runs under Apache with `mod_wsgi` inside a container.

# Installation
The mPCC is installed as part of the full mProv stack using [mprov-compose](https://github.com/mprov-ng/mprov-compose), which starts the mPCC, its database, and a jobserver on a single node with Docker.  Follow the instructions in the mprov-compose README.

Note: The old bare-metal installer (`install_mpcc.sh`) has been removed and is no longer supported.  It also set up an NFS-exported `/export/mprov` share, built Slurm into it, and installed MLX OFED, NVIDIA drivers and Ansible on the mPCC host.  None of that is provided by the containerized install.  If you need those, set them up separately.

# Post installation
The successfully installed mPCC admin UI is available at http://<FQDN or IP>/admin/login/?next=/admin/ . The default credentials are admin / admin. 
Once the installation is complete, it is highly suggested that you create an API Key and get a job server running, https://github.com/mprov-ng/mprov_jobserver/blob/main/README.md

When creating an API key in the mPCC, you only need to specify a name for the API key, the expire times are only if your security protocols dictate the need for expiring keys.
