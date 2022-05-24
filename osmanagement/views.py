from common.views import MProvView
from osmanagement.models import OSDistro, OSRepo
from osmanagement.serializers import OSDistroAPISerializer, OSRepoAPISerializer
from jobqueue.models import Job, JobModule
from pprint import pprint

class OSDistroAPIView(MProvView):
    '''
# /distros/

## Accepted HTTP Methods:
- GET (no parameters)
- GET (with Primary Key, ie: /distros/1/)
- POST (with primary key, ie: /distros/1/)
- PATCH (with primary key, ie: /distros/1/)
- DELETE (with primary key, ie: /distros/1/)

## Documentation

### Class Attributes
- id: The internal ID in the db
- name: A human readable name 
- vendor: A name for the vendor of this OS
- version: The version for this OS, used to pull base repos.
- config_params: (Optional) YAML of config params for this OS distro, least priority 
- install_kernel_cmdline: (Optional) The commandline passed to the kernel when it boots on a system
- baserepo: the ID of the baserepo from the DB to suse to generate the image
- osrepos: (Optional) Repos to be added during image generation
- scripts: (Optional) Scripts that will run  on images/systems using this  OS

### GET method (no parameters)
Returns a json list of all objects in the MPCC of this type

Format returned:

    [
    {
        "id": 1,
        "name": "Rocky Linux 8 Latest",
        "vendor": "Rocky Linux",
        "version": "8",
        "config_params": "rootpw: 'root:$6$80Lz0whR9xNVPouX$L3wyFx7h3oYS9RvzFTVJLFUkjApUCJ3kH5KtOUZgREMEDp7owSxVq5NlFCcR9s3knaz7g4YuCXBiqcbQJGRl91'
                          extra_packages: 
                            - vim-enhanced
                            - wget
                            - epel-release",
        "install_kernel_cmdline": "mprov_tmpfs_size=8G mprov_image_url=http://${next-server}/images/{{ nic.system.systemimage.slug }} mprov_initial_mods=e1000e,tg3 mprov_prov_intf=eth0",
        "baserepo": 1,
        "osrepos": [],
        "scripts": [
        "install_postboot_jobserversh",
        "install_yqsh",
        "set_root_pwsh"
        ]
    }
    ]

### GET, POST, PATCH, DELETE (with primary key)
- These methods, when passed a primary key, will Retrieve, Create, Update, or 
    Delete that entry in the database.  POST requires ALL required fields.  PATCH
    will only update the fields passed, required fields can be omitted if changed.

- GET returns the object specified or 404

- POST returns the new object created or a 500 style error

- PATCH returns the updated object.

- DELETE returns 204 No Content if the delete is successful.

    '''    
    model = OSDistro 
    template = 'osdistro_docs.html'
    serializer_class = OSDistroAPISerializer
    queryset = OSDistro.objects.all()

class OSRepoAPIView(MProvView):
    '''
# /repos/

## Accepted HTTP Methods:
- GET (no parameters)
- GET (with Primary Key, ie: /repos/1/)
- POST (with primary key, ie: /repos/1/)
- PATCH (with primary key, ie: /repos/1/)
- DELETE (with primary key, ie: /repos/1/)

## Documentation

### Class Attributes
- id: The internal ID in the db
- name: A human readable name 
- repo_package_url: The URL of the repo install package
- osdistro: (Optional) OS Distros this is associated with


### GET method (no parameters)
Returns a json list of all objects in the MPCC of this type

Format returned:

    [
    {
        "id": 1,
        "name": "Rocky Linux 8.5 OS",
        "repo_package_url": "https://distro.ibiblio.org/rocky/8.5/BaseOS/x86_64/os/Packages/r/rocky-repos-8.5-3.el8.noarch.rpm",
        "osdistro": []
    }
    ]

### GET, POST, PATCH, DELETE (with primary key)
- These methods, when passed a primary key, will Retrieve, Create, Update, or 
    Delete that entry in the database.  POST requires ALL required fields.  PATCH
    will only update the fields passed, required fields can be omitted if changed.

- GET returns the object specified or 404

- POST returns the new object created or a 500 style error

- PATCH returns the updated object.

- DELETE returns 204 No Content if the delete is successful.

    '''   
    model = OSRepo
    template = 'osrepo_docs.html'
    serializer_class = OSRepoAPISerializer
    queryset = OSRepo.objects.all()