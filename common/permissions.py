from rest_framework.permissions import IsAuthenticated
from rest_framework_api_key.permissions import HasAPIKey

# A logged-in user (session or basic auth) OR the API key (#272).  The
# project's DRF default and MProvView both use this; a tuple of the two in
# DEFAULT_PERMISSION_CLASSES would need both.
HasAPIKeyOrIsAuthenticated = HasAPIKey | IsAuthenticated
