== mProv Control Center (mPCC) ==

This document will serve as a general installation document for mProv Control Center, mPCC.  Please note, this document will be centered around Rocky Linux 8.  You may need to adapt the proceedures here if you are using a different RHEL based distro.  

=== Prerequisits ===
Currently, mPCC only supports RHEL derivatives.  Support for other Linux derivatives is planned.

You will also need:
- Python 3.8 or higher.
- A database of some kind that will work with Django
- A web server of some design

It is recommended to use a python venv for the mPCC.  You can easily set one up with `python3.8 -m venv .` to create a python 3.8 venv in the current directory.

In addition ot the items listed above, you will also need the python packages listed in the requirements.txt file.  You can easily install them after cloning the repository with the `pip install -r requirements.txt` command or if you use the `install_mpcc.sh` script below, it will be done for you.

Installation of most of the prerequisit software can be accomplished with the following dnf command:
```# dnf -y install python38-mod_wsgi.x86_64 ipmitool dnsmasq ipxe-bootimgs.noarch jq golang```
Note: The `install_mpcc.sh` will do this for you.


=== Installation ===
It is HIGHLY recommended to use the `install_mpcc.sh` script if you are installing into a RHEL-8 derivative (ie: Rocky Linux 8).

