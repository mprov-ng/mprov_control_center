#!/bin/bash 
# clear the env.
wget https://raw.githubusercontent.com/mprov-ng/mprov_jobserver/main/install_mprov_jobserver.sh -O - | sudo su - -c /bin/bash


cat << EOF > /tmp/genAPIKey.py
import rest_framework_api_key
apikey = rest_framework_api_key.models.APIKey()
key = rest_framework_api_key.models.APIKey.objects.assign_key(apikey)
apikey.name="mProv Jobserver Key"
apikey.save()
print(key)
EOF

apikey=`cat /tmp/genAPIKey.py | python3 manage.py shell`
hostname=`hostname`
cat << EOF > /etc/mprov/jobserver.yaml
- global:
    # This points to your mprov control center instance.
    # This URL should point to the internal IP address or hostname and include a trailing slash
    # e.g. "http://<IP of internal interface>/"
    
    mprovURL: "http://$hostname"
    # this is the api key for your mprov control center so that the 
    # jobserver can login and do stuff.
    apikey: '$apikey'
    # this is the interval which this jobserver will check in with the mPCC
    heartbeatInterval: 10
    # runonce: True # uncomment to run the jobserver once and exit.
    myaddress: '' # set this to the address of this jobserver.
    jobmodules:
      # set the jobmodules you want to run here.
      - repo-delete
      - repo-update
      - image-update # REQUIRES mprov-webserver
      - mprov-webserver
      - image-delete
      - dnsmasq
      - libgenders

# include any plugin yamls.        
- !include plugins/*.yaml
EOF

# start the job server.
systemctl start mprov_jobserver
