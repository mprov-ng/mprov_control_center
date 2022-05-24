from django.shortcuts import render
from common.views import MProvView
from .models import Script
from .serializers import ScriptAPISerializer

class ScriptAPIView(MProvView):
  '''
# /scripts/

## Accepted HTTP Methods:
- GET (no parameters)
- GET (with Primary Key, ie: /scripts/script-slug/)
- POST (with primary key, ie: /scripts/script-slug/)
- PATCH (with primary key, ie: /scripts/script-slug/)
- DELETE (with primary key, ie: /scripts/script-slug/)

## Documentation

### Class Attributes

- slug: The slug ID of this script
- name: A human readable name for this script, usually a filename
- filename: The URL to where you can get this script
- version: The version, used for tracking script changes
- scriptType: One of "image-gen" or "post-boot"
- dependsOn: Array of other script's slugs this script depends on.

### GET method (no parameters)
Returns a json list of all objects in the MPCC of this type

Format returned:

    [
      {
        "slug": "set_root_pwsh",
        "name": "set_root_pw.sh",
        "filename": "http://10.99.130.149/media/set_root_pwsh-v10",
        "version": 10,
        "scriptType": "image-gen",
        "dependsOn": []
      },
      {
        "slug": "install_yqsh",
        "name": "install yq",
        "filename": "http://10.99.130.149/media/install_yqsh-v3",
        "version": 3,
        "scriptType": "image-gen",
        "dependsOn": []
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
  model = Script
  template = "scripts_docs.html"
  serializer_class = ScriptAPISerializer
  queryset = Script.objects.all()
