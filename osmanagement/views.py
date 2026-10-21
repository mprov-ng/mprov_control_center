from common.views import MProvView
from osmanagement.models import OSDistro, OSRepo, OSType
from osmanagement.serializers import OSDistroAPISerializer, OSRepoAPISerializer, OSTypeAPISerializer
from rest_framework.response import Response

class OSDistroAPIView(MProvView):
    '''
# /distros/

## Accepted HTTP Methods:
- GET (no primary key)
- GET (with Primary Key, e.g. /distros/1/)
- POST (no primary key, e.g. /distros/)
- PATCH (with primary key, e.g. /distros/1/)
- DELETE (with primary key, e.g. /distros/1/)

## Documentation

### Class Attributes
- id: The internal ID in the db
- name: A human-readable name 
- vendor: A name for the vendor of this OS
- version: The version for this OS, used to pull base repos.
- config_params: (Optional) YAML of config params for this OS distro, lowest priority
- install_kernel_cmdline: (Optional) The command line passed to the kernel when it boots on a system
- baserepo: The ID of the base repo from the DB used to generate the image
- osrepos: (Optional) Repos to be added during image generation
- scripts: (Optional) Scripts that will run on images/systems using this OS
- distType: (Optional) The slug of the OS type
- distArch: The CPU architecture (x86_64, aarch64, ppc64le, or s390x)
- managed: Whether repos generated for this distro are mProv managed
- update: If true, saving the distro creates/updates its AppStream, BaseOS, extras,
    CRB (version 9+) or PowerTools, and EPEL repos from baseurl, then resets to false
- baseurl: The base URL the generated repos are built from
- extrarepos: (Optional) IDs of extra repos
- rootpw: (Optional) Root password for the image
- rootsshkeys: (Optional) Keys to add to root's authorized keys file
- ansibleplaybooks, ansibleroles, ansiblecollections: (Optional) Ansible content
    to run on images/systems using this OS
- tmpfs_root_size: Size of the root tmpfs filesystem, in GB
- initial_mods: Comma-separated list of kernel modules to load
- prov_interface: Interface name to provision over

### Query Parameters
- ?detail: GET (no primary key) returns entries with related objects nested 3 levels deep, as for a single entry.

### GET method (no primary key)
Returns a JSON list of all objects of this type in the mPCC, or 404 if there are
none.  Any field of this type can be passed as a query parameter to filter the
list (e.g. ?name=example).

Format returned:

    [
    {
        "id": 1,
        "name": "Rocky Linux 8 Latest",
        "vendor": "Rocky Linux",
        "version": "8",
        "config_params": "rootpw: 'root:$6$<salt>$<hash>'
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

### GET, PATCH, DELETE (with primary key) and POST (without primary key)
- GET, PATCH, and DELETE, when passed a primary key, will Retrieve, Update, or
    Delete that entry in the database.  POST is sent to the base URL (no primary
    key) and will Create a new entry; it requires ALL required fields.  PATCH
    will only update the fields passed; fields that are not changing can be omitted.

- GET returns the object specified, with related objects nested 3 levels deep, or 404

- POST returns the new object created, or a 400 error if validation fails

- PATCH returns the updated object.

- DELETE returns 204 No Content if the delete is successful.

    '''    
    model = OSDistro 
    serializer_class = OSDistroAPISerializer
    queryset = OSDistro.objects.all()

class OSRepoAPIView(MProvView):
    '''
# /repos/

## Accepted HTTP Methods:
- GET (no primary key)
- GET (with Primary Key, e.g. /repos/1/)
- POST (no primary key, e.g. /repos/)
- PATCH (with primary key, e.g. /repos/1/)
- DELETE (with primary key, e.g. /repos/1/)

## Documentation

### Class Attributes
- id: The internal ID in the db
- name: A human-readable name 
- repo_package_url: The URL of the repo install package
- managed: Whether mProv downloads and manages this repo
- update: If true (and managed), saving queues a repo-update job, bumps the
    version, and clears hosted_by
- hosted_by: IDs of the job servers hosting this repo
- ostype: (Optional) The slug of the OS type
- version: Local version of the repo, if mProv managed


### Query Parameters
- ?detail: GET (no primary key) returns entries with related objects nested 3 levels deep, as for a single entry.

### GET method (no primary key)
Returns a JSON list of all objects of this type in the mPCC, or 404 if there are
none.  Any field of this type can be passed as a query parameter to filter the
list (e.g. ?name=example).

Format returned:

    [
    {
        "id": 1,
        "name": "Rocky Linux 8.5 OS",
        "repo_package_url": "https://distro.ibiblio.org/rocky/8.5/BaseOS/x86_64/os/Packages/r/rocky-repos-8.5-3.el8.noarch.rpm",
        "managed": false,
        "update": false,
        "hosted_by": [],
        "ostype": null,
        "version": 1
    }
    ]

### GET, PATCH, DELETE (with primary key) and POST (without primary key)
- GET, PATCH, and DELETE, when passed a primary key, will Retrieve, Update, or
    Delete that entry in the database.  POST is sent to the base URL (no primary
    key) and will Create a new entry; it requires ALL required fields.  PATCH
    will only update the fields passed; fields that are not changing can be omitted.

- GET returns the object specified, with related objects nested 3 levels deep, or 404

- POST returns the new object created, or a 400 error if validation fails

- PATCH returns the updated object.

- DELETE returns 204 No Content if the delete is successful.

    '''   
    model = OSRepo
    serializer_class = OSRepoAPISerializer
    queryset = OSRepo.objects.all()

    
class OSTypeAPIView(MProvView):
    '''
# /ostypes/

## Accepted HTTP Methods:
- GET (no primary key)
- GET (with Primary Key, e.g. /ostypes/rhel/)
- POST (no primary key, e.g. /ostypes/)
- PATCH (with primary key, e.g. /ostypes/rhel/)
- DELETE (with primary key, e.g. /ostypes/rhel/)

## Documentation

### Class Attributes
- slug: The internal ID in the db
- name: A human-readable name 


### Query Parameters
- ?detail: GET (no primary key) returns entries with related objects nested 3 levels deep, as for a single entry.

### GET method (no primary key)
Returns a JSON list of all objects of this type in the mPCC, or 404 if there are
none.  Any field of this type can be passed as a query parameter to filter the
list (e.g. ?name=example).

Format returned:

    [
    {
        "slug": "rhel",
        "name": "Yum/dnf based Linux OS"
    }
    ]

### GET, PATCH, DELETE (with primary key) and POST (without primary key)
- GET, PATCH, and DELETE, when passed a primary key, will Retrieve, Update, or
    Delete that entry in the database.  POST is sent to the base URL (no primary
    key) and will Create a new entry; it requires ALL required fields.  PATCH
    will only update the fields passed; fields that are not changing can be omitted.

- GET returns the object specified, with related objects nested 3 levels deep, or 404

- POST returns the new object created, or a 400 error if validation fails.
    If an OS type with the given slug already exists, its name is updated
    instead and 200 is returned with an empty body.

- PATCH returns the updated object.

- DELETE returns 204 No Content if the delete is successful.

    '''   
    model = OSType
    serializer_class = OSTypeAPISerializer
    queryset = OSType.objects.all()

    def post(self, request, *args, **kwargs):
        if 'slug' in request.data:
            queryset = OSType.objects.all().filter(pk=request.data['slug'])
            if queryset.count() > 0:
                # update the entry
                obj = queryset[0]
                obj.name = request.data['name']
                obj.save()
                return Response(None, status=200)
        
        return super().post(request, *args, **kwargs)
