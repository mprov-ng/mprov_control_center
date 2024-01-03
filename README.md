
# mProv Control Center
![Buidl Status](https://img.shields.io/github/actions/workflow/status/mprov-ng/mprov_control_center/dockerimages.yml?style=plastic)
![Latest Version](https://img.shields.io/github/v/tag/mprov-ng/mprov_control_center?style=plastic)
![License](https://img.shields.io/github/license/mprov-ng/mprov_control_center?style=plastic)

The mProv Control Center (mPCC) is the heart of everything that mProv manages. It is the brains that runs everything through a web interface, thusly allowing for ease of use. mProv runs a REST/CRUD API for interfacing to the database and allowing remote access. 

The mPCC performs a wide range of jobs, permissions, and maintenance:
- Authentication
- Networking
- Issuing jobs to the mprov_jobservers
- An endpoint for serving files to nodes that require PXE booting 
- Running scripts to nodes post boot

The mPCC is based off of Django 3.2. You will need to run a Python web app server to then run the Django code. The installation proceedure found below will walk you through most of the necessary steps, including installing Apache with `python38-mod_wsgi`. This version of mPCC requires Python-3.8 or higher, however we are still testing with versions 3.9 and higher.

## Requirements
- The mPCC requires python 3.8 and above.  
- At this time, mPCC also requires to be run in a RHEL derivative (i.e. Rocky Linux 8)
- A system running Rocky Linux 8 with at least the 'Minimal Install' package group installed.
- If you are using a database server, you will need the database running with the user(s) and database already configured for access.
- SELinux should also be disabled or permissive (Enforcing SELinux currently causes issues)

# Installation
This installation proceedure assumes that you have a system with at least the "Minimal Install" packages installed.  You can have more than that, but the installer assumes it will have to handle most of the dependancy installaion.

If you download the installer and run it, it will create an `env.db` file for you if one doesn't exist.  You should modify this file and re-run the installer to install the mPCC.



Installation is best done by downloading [install_mpcc.sh](https://raw.githubusercontent.com/mprov-ng/mprov_control_center/main/install_scripts/install_mpcc.sh) and running it as root.  This script takes the following arguments:

- -d: Run as if you were building a docker image, meaning don't run init_mpcc.sh
- -m: Install the stuff necessary to use a MariaDB backend.
- -p: Install the stuff necessary to use a PostgreSQL backend.
- -x: Passing this flag will check out the `main` branch of this repository.  Without it, it will checkout the latest Release tag.  Use this flag for development only!

Note: Passing neither `-m` or `-p` will default to an SQLite backend that will be stored in the `db/` directory.


Example: `./install_mpcc.sh -m` will install the mPCC to the machine it is run on, with all the dependencies, and set it up to run a mariadb back end.  

Once everything is setup, you will want to add the necessary IP and hostnames for the machine to the .env file in /var/www/mprov_control_center/ for the `ALLOWED_HOSTS` variable.  This is a comma separated list of IP's and/or fqdns that mPCC will reply to.  If you skip this step, you will not be able to access mPCC.


## Docker
Docker images exist for the mPCC as well.  More information on how to use the docker images will be coming soon, so keep an eye out for that.  Basically, setting the right env vars, and running the docker image with the right exposed port should be enough to get it running.  There are images for: SQLite implementations, MariaDB implementations, and PostgreSQL implementations.  You will probably want to bind mount the following directories for data persistence:

- /var/www/mprov_control_center/db : where the SQLite implementation stores it's DB
- /var/www/mprov_control_center/media : Where scripts get stored.

# Post installation
The succesfully installed MPCC admin UI is available at http://<FQDN or IP>/admin/login/?next=/admin/ . The default credntails are admin / admin. 
Once you have the installation installed, it is highly suggested that you create an API Key and get a job server running, https://github.com/mprov-ng/mprov_jobserver/blob/main/README.md
