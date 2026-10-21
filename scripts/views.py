from common.views import MProvView
from .models import Script, File, AnsiblePlaybook, AnsibleRole, AnsibleCollection
from .serializers import (
  ScriptAPISerializer,
  FileAPISerializer,
  AnsiblePlaybookAPISerializer,
  AnsibleRoleAPISerializer,
  AnsibleCollectionAPISerializer,
)

class ScriptAPIView(MProvView):
  '''
# /scripts/

## Accepted HTTP Methods:
- GET (no primary key)
- GET (with Primary Key, e.g. /scripts/script-slug/)
- POST (no primary key, e.g. /scripts/)
- PATCH (with primary key, e.g. /scripts/script-slug/)
- DELETE (with primary key, e.g. /scripts/script-slug/)

## Documentation

### Class Attributes

- slug: The slug ID of this script
- name: A human-readable name for this script, usually a filename
- filename: The URL where you can get this script
- content: Always empty; the script body is stored in the file, not the database
- version: The version, used for tracking script changes
- scriptType: The script type, as a nested object with its name and slug (e.g. "image-gen" or "post-boot").
    Send the slug on POST and PATCH.
- dependsOn: Array of other scripts' slugs this script depends on.

### Query Parameters
- ?detail: GET (no primary key) returns entries with related objects nested 3 levels deep, as for a single entry.

### GET method (no primary key)
Returns a JSON list of all objects of this type in the mPCC, or 404 if there are
none.  Any field of this type can be passed as a query parameter to filter the
list (e.g. ?name=example).

Format returned:

    [
      {
        "slug": "set_root_pwsh",
        "name": "set_root_pw.sh",
        "filename": "http://127.0.0.1/media/image-gen/set_root_pwsh-v10",
        "version": 10,
        "content": "",
        "scriptType": {"name": "Image Generation", "slug": "image-gen"},
        "dependsOn": []
      },
      {
        "slug": "install_yqsh",
        "name": "install yq",
        "filename": "http://127.0.0.1/media/image-gen/install_yqsh-v3",
        "version": 3,
        "content": "",
        "scriptType": {"name": "Image Generation", "slug": "image-gen"},
        "dependsOn": []
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
  model = Script
  serializer_class = ScriptAPISerializer
  queryset = Script.objects.all()


class FileAPIView(MProvView):
  '''
# /files/

## Accepted HTTP Methods:
- GET (no primary key)
- GET (with Primary Key, e.g. /files/file-slug/)
- POST (no primary key, e.g. /files/)
- PATCH (with primary key, e.g. /files/file-slug/)
- DELETE (with primary key, e.g. /files/file-slug/)

## Documentation

### Class Attributes
- slug: The slug ID of this file.  Optional on POST; made from the file name if not given.
- name: A human-readable name for this file
- filename: The uploaded file; GET returns the URL where you can get it.  Send it as a multipart upload.
- version: The version, used for tracking file changes

### Query Parameters
- ?detail: GET (no primary key) returns entries with related objects nested 3 levels deep, as for a single entry.

### GET method (no primary key)
Returns a JSON list of all objects of this type in the mPCC, or 404 if there are
none.  Any field of this type can be passed as a query parameter to filter the
list (e.g. ?name=example).

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
  model = File
  serializer_class = FileAPISerializer
  queryset = File.objects.all()


class AnsiblePlaybookAPIView(MProvView):
  '''
# /ansibleplaybook/

## Accepted HTTP Methods:
- GET (no primary key)
- GET (with Primary Key, e.g. /ansibleplaybook/playbook-slug/)
- POST (no primary key, e.g. /ansibleplaybook/)
- PATCH (with primary key, e.g. /ansibleplaybook/playbook-slug/)
- DELETE (with primary key, e.g. /ansibleplaybook/playbook-slug/)

## Documentation

### Class Attributes
- slug: The slug ID of this playbook.  Optional on POST; made from the file name if not given.
- name: A human-readable name for this playbook
- filename: The uploaded playbook; GET returns the URL where you can get it.  Send it as a multipart upload.
- scriptType: The type, as a nested object with its name and slug (e.g. "image-gen" or "post-boot").
    Send the slug on POST and PATCH.
- version: The version, used for tracking playbook changes
- dependsOn: Array of the slugs of other entries of this type that this one depends on.

### Query Parameters
- ?detail: GET (no primary key) returns entries with related objects nested 3 levels deep, as for a single entry.

### GET method (no primary key)
Returns a JSON list of all objects of this type in the mPCC, or 404 if there are
none.  Any field of this type can be passed as a query parameter to filter the
list (e.g. ?name=example).

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
  model = AnsiblePlaybook
  serializer_class = AnsiblePlaybookAPISerializer
  queryset = AnsiblePlaybook.objects.all()


class AnsibleRoleAPIView(MProvView):
  '''
# /ansiblerole/

## Accepted HTTP Methods:
- GET (no primary key)
- GET (with Primary Key, e.g. /ansiblerole/role-slug/)
- POST (no primary key, e.g. /ansiblerole/)
- PATCH (with primary key, e.g. /ansiblerole/role-slug/)
- DELETE (with primary key, e.g. /ansiblerole/role-slug/)

## Documentation

### Class Attributes
- slug: The slug ID of this role.  Optional on POST; made from the role URL if not given.
- name: A human-readable name for this role
- roleurl: A git repository URL holding a single role, or an Ansible Galaxy role name
- scriptType: The type, as a nested object with its name and slug (e.g. "image-gen" or "post-boot").
    Send the slug on POST and PATCH.
- version: The version, used for tracking role changes
- dependsOn: Array of the slugs of other entries of this type that this one depends on.

### Query Parameters
- ?detail: GET (no primary key) returns entries with related objects nested 3 levels deep, as for a single entry.

### GET method (no primary key)
Returns a JSON list of all objects of this type in the mPCC, or 404 if there are
none.  Any field of this type can be passed as a query parameter to filter the
list (e.g. ?name=example).

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
  model = AnsibleRole
  serializer_class = AnsibleRoleAPISerializer
  queryset = AnsibleRole.objects.all()


class AnsibleCollectionAPIView(MProvView):
  '''
# /ansiblecollection/

## Accepted HTTP Methods:
- GET (no primary key)
- GET (with Primary Key, e.g. /ansiblecollection/collection-slug/)
- POST (no primary key, e.g. /ansiblecollection/)
- PATCH (with primary key, e.g. /ansiblecollection/collection-slug/)
- DELETE (with primary key, e.g. /ansiblecollection/collection-slug/)

## Documentation

### Class Attributes
- slug: The slug ID of this collection.  Optional on POST; made from the collection URL if not given.
- name: A human-readable name for this collection
- collectionurl: The Ansible Galaxy collection name
- scriptType: The type, as a nested object with its name and slug (e.g. "image-gen" or "post-boot").
    Send the slug on POST and PATCH.
- version: The version, used for tracking collection changes
- dependsOn: Array of the slugs of other entries of this type that this one depends on.

### Query Parameters
- ?detail: GET (no primary key) returns entries with related objects nested 3 levels deep, as for a single entry.

### GET method (no primary key)
Returns a JSON list of all objects of this type in the mPCC, or 404 if there are
none.  Any field of this type can be passed as a query parameter to filter the
list (e.g. ?name=example).

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
  model = AnsibleCollection
  serializer_class = AnsibleCollectionAPISerializer
  queryset = AnsibleCollection.objects.all()
