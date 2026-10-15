# Install Scripts
These scripts are run inside the mPCC container.  `init_mpcc.sh` is the container's entrypoint: it runs the database migrations, and on first start it creates the admin user, registers the mPCC host, generates the jobserver API key and calls `load_default_scripts.sh` to import the scripts from [mprov_scripts](https://github.com/mprov-ng/mprov_scripts).
