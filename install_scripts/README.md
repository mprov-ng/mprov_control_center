# Install Scripts
This directory contains a few scripts that may or may not be run at install time.  The `install.d` directory will be read by 
the installer and ordered by name appended with a number.  All scripts in this directory SHOULD be tested for idempotence. Scripts should also source the .env directory to get configuration set by the user.