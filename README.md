
# mProv Control Center
![Buidl Status](https://img.shields.io/github/actions/workflow/status/mprov-ng/mprov_control_center/dockerimages.yml?style=plastic)
![Latest Version](https://img.shields.io/github/v/tag/mprov-ng/mprov_control_center?style=plastic)
![License](https://img.shields.io/github/license/mprov-ng/mprov_control_center?style=plastic)

The heart of the mProv management suite, the mProv Control Center (mPCC) is the brains behind everything that mProv manages.  It's what runs the web interface, for ease of use.  It runs a REST CRUD API for interfaces to the database and remotely doing stuff.  It manages authentication, jobs to the mprov_jobservers, and serves as a endpoint for serving up files needed for PXE booting and running scripts on nodes post boot.

The mPCC is based off of django 3.2.  You will need to run a python web app server to run the django code.  The installation proceedure below will walk you through most of that, installing Apache with `python38-mod_wsgi`.  This version of the mPCC requires python-3.8 or greater, but hasn't been tested yet with versions greater than 3.9.

## Requirements
- The mPCC requires python 3.8 and above.  
- At this time, mPCC also requires to be run in a RHEL derivative (i.e. Rocky Linux 8)
- A system running with at least the Minimal Install
- If you are using a database server, you will need the database running with the user and database already configured for access.
- SELinux should also be disabled or permissive.  Enforcing SELinux currently causes issues.

# Installation
This installation proceedure assumes that you have a system with at least the "Minimal Install" packages installed.  You can have more than that, but the installer assumes it will have to handle most of the dependancy installaion.

If you download the installer and run it, it will create an `env.db` file for you if one doesn't exist.  You should modify this file and re-run the installer to install the mPCC.



Installation is best done by cloning the repository and running `./install_mpcc.sh` as root.  This script takes the following arguments:

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
Once you have the installation installed, it is highly suggested that you create an API Key and get a job server running..
