import logging
import os
import sys

from django.apps import AppConfig
from django.conf import settings


class PkiConfig(AppConfig):
    """ The pki app: the mPCC's own CA, its HTTPS certificate and the agents'
    credentials (#381). """
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'pki'
    verbose_name = "Agent Identities"

    def ready(self):
        from common.permissions import SHARED_KEY_MODES
        # once in the web server's log, not on every manage.py command
        if os.path.basename(sys.argv[0] if sys.argv else "") == "manage.py":
            return
        log = logging.getLogger("mprov.auth")
        mode = getattr(settings, "MPROV_SHARED_KEY_MODE", "off")
        if mode not in SHARED_KEY_MODES:
            log.error(f"MPROV_SHARED_KEY_MODE={mode!r} isn't one of {', '.join(SHARED_KEY_MODES)}; "
                      "the shared API key is refused.")
        elif mode == "all":
            log.warning("MPROV_SHARED_KEY_MODE=all: the shared API key is accepted everywhere, as before 0.7. "
                        "Unset it (the default is \"off\") once job servers and node images use their own "
                        "credentials; 0.8.0 removes the key.")
        elif mode == "nodes":
            log.warning("MPROV_SHARED_KEY_MODE=nodes: the shared API key is accepted only for what a node "
                        "does to itself, until every image is rebuilt; unset it (the default is \"off\") then.")
