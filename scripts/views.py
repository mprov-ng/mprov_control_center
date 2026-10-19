from django.shortcuts import render
from common.views import MProvView
from .models import Script
from .serializers import ScriptAPISerializer

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

- GET returns the object specified or 404

- POST returns the new object created, or a 400 error if validation fails

- PATCH returns the updated object.

- DELETE returns 204 No Content if the delete is successful.

    '''
  model = Script
  serializer_class = ScriptAPISerializer
  queryset = Script.objects.all()
