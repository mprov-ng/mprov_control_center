#!/usr/bin/env python3
"""
A booting node's own credential (#381).

mprov_boot_init.sh downloads this next to genNetworkInterfaces.py and
mprov_stateful.py, which import it.  On a provisioning boot, /ipxe/ put two
parameters on the kernel command line:
- mprov_enroll=<nonce>: one-time, for this boot, from this address;
- mprov_ca=<SHA-256 of the mPCC's CA certificate>.

enroll() downloads the CA certificate and checks it against mprov_ca, makes a
key and a CSR with openssl (the key never leaves the node), sends the CSR with
the nonce to the mPCC over HTTPS, and keeps the key, the certificate and the
CA certificate in /etc/mprov/tls/.  The stateful installer copies the running
root to disk, so an installed node keeps them too.

use(session, url) then points a requests session at the mPCC over HTTPS with
that certificate.  When there's nothing to enroll with (an mPCC before 0.7, a
N.A.D.S. boot) or enrollment fails, the scripts carry on with the shared API
key, as before, and say why.

Images also install this file and run it at boot and daily, to keep the
credential current:

  mprov_enroll.py renew    renew it in its last RENEW_DAYS days; if it has
                           expired, re-enroll through a window an admin opened
                           ("Let these systems re-enroll" in the mPCC)
  mprov_enroll.py status   show when it expires

Both exit 0 when there's nothing to do, including on a node without a
credential.
"""
import base64
import hashlib
import json
import os
import random
import re
import subprocess
import tempfile
import time
from urllib.parse import urlsplit, urlunsplit

TLS_DIR = "/etc/mprov/tls"
KEY, CERT, CA, URL = "node.key", "node.crt", "ca.crt", "mpcc_url"
# renew this many days before the credential expires (the mPCC allows 15)
RENEW_DAYS = 14
# A fleet boot can briefly overload the mPCC (a 502/503/504 or a dropped
# connection) and it recovers seconds later, so a booting node tries its
# enrollment calls this many times, waiting about BACKOFF seconds before the
# second try and twice as long before each next one (#536).
TRIES = 5
BACKOFF = 2
RETRY_STATUSES = (502, 503, 504)


def kernel_params(path="/proc/cmdline"):
  """ mprov_enroll and mprov_ca from the kernel command line, or Nones. """
  try:
    with open(path) as f:
      words = f.read().split()
  except OSError:
    return None, None
  params = dict(w.split("=", 1) for w in words if "=" in w)
  nonce, ca = params.get("mprov_enroll"), params.get("mprov_ca")
  if nonce and not re.fullmatch(r"[0-9a-f]{32}", nonce):
    nonce = None
  if ca and not re.fullmatch(r"[0-9a-f]{64}", ca):
    ca = None
  return nonce, ca


def https_url(url):
  """ The mPCC's HTTPS URL for its plain-HTTP one: same host, port 443. """
  parts = urlsplit(url)
  host = parts.hostname or ""
  if ":" in host:
    host = f"[{host}]"
  return urlunsplit(("https", host, parts.path or "/", "", ""))


def http_url(url):
  """ Where to download the CA certificate from: url itself if it's plain
  HTTP, else the same host over HTTP on port 80.  A node can't check the
  mPCC's HTTPS certificate before it has the CA; the CA is trusted by its
  fingerprint (mprov_ca) instead. """
  parts = urlsplit(url)
  if parts.scheme == "http":
    return url.rstrip("/") + "/"
  host = parts.hostname or ""
  if ":" in host:
    host = f"[{host}]"
  return urlunsplit(("http", host, parts.path or "/", "", ""))


def pem_fingerprint(pem):
  """ The SHA-256 fingerprint of the first certificate in pem, in lowercase hex. """
  match = re.search(r"-----BEGIN CERTIFICATE-----(.+?)-----END CERTIFICATE-----", pem, re.S)
  if match is None:
    raise ValueError("not a PEM certificate")
  return hashlib.sha256(base64.b64decode("".join(match.group(1).split()))).hexdigest()


def have(tls_dir=TLS_DIR):
  """ True if this node has an enrolled key, certificate and CA in tls_dir. """
  return all(os.path.isfile(os.path.join(tls_dir, f)) for f in (KEY, CERT, CA))


def _write(path, data, mode):
  """ Write data to path, created or truncated, with mode (also applied to an
  existing file). """
  fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode)
  with os.fdopen(fd, "w") as f:
    f.write(data)
  os.chmod(path, mode)


def make_csr(key_path):
  """ A new EC P-256 key at key_path (0600) and its CSR, in PEM. """
  old = os.umask(0o077)
  try:
    result = subprocess.run(
      ["openssl", "req", "-new", "-newkey", "ec", "-pkeyopt", "ec_paramgen_curve:prime256v1",
       "-nodes", "-keyout", key_path, "-subj", "/CN=mprov-node"],
      capture_output=True, text=True, check=True)
  finally:
    os.umask(old)
  os.chmod(key_path, 0o600)
  return result.stdout


def _never_connected(error):
  """ Whether a requests ConnectionError happened before the request was sent:
  the connection timed out or was refused, so the mPCC never saw it. """
  import requests
  from urllib3.exceptions import NewConnectionError
  if isinstance(error, requests.exceptions.ConnectTimeout):
    return True
  reason = getattr(error.args[0], "reason", None) if error.args else None
  return isinstance(reason, NewConnectionError)


def _send(call, what, log, sleep, resend_after_reply_lost):
  """ call() until the mPCC answers with something other than RETRY_STATUSES or
  the request fails to get through, up to TRIES times, with backoff and
  jitter.  Returns (the last reply, whether an earlier try may have reached
  the mPCC and been acted on although its reply was lost).

  A connection that couldn't be made, or a 502/503/504, didn't change
  anything on the mPCC.  A read timeout or a connection dropped mid-request
  may have: unless resend_after_reply_lost, the request isn't sent again and
  a read timeout is raised; a dropped connection is retried, as it's far more
  likely to be an overloaded mPCC closing it unread, but reported as maybe
  acted on.  The last try's exception is raised if none got a reply. """
  import requests
  maybe_acted_on = False
  for attempt in range(TRIES):
    try:
      reply = call()
      if reply.status_code not in RETRY_STATUSES or attempt == TRIES - 1:
        return reply, maybe_acted_on
      problem = f"the mPCC answered {reply.status_code}"
      maybe_acted_on = maybe_acted_on or reply.status_code == 504
    except requests.exceptions.ReadTimeout:
      if not resend_after_reply_lost or attempt == TRIES - 1:
        raise
      problem = "no reply in time"
    except requests.exceptions.SSLError:
      # a certificate that doesn't check out won't on a retry either
      raise
    except requests.exceptions.ConnectionError as e:
      if attempt == TRIES - 1:
        raise
      if not _never_connected(e):
        maybe_acted_on = True
      problem = f"couldn't reach the mPCC ({e.__class__.__name__})"
    wait = BACKOFF * 2 ** attempt * random.uniform(0.5, 1.5)
    log(f"{what}: {problem}; trying again in {wait:.0f}s ({attempt + 2} of {TRIES}).")
    sleep(wait)


def enroll(session, mprov_url, cmdline="/proc/cmdline", tls_dir=TLS_DIR, log=print, sleep=time.sleep):
  """ Enroll this boot, if it was given a nonce.  True when the node has its
  credential in tls_dir afterwards.  A brief overload of the mPCC is retried
  (#536). """
  nonce, ca_fp = kernel_params(cmdline)
  if nonce is None or ca_fp is None:
    log("No enrollment parameters on the kernel command line; using the shared API key.")
    return False
  try:
    # no API key: this download isn't an agent's API call
    response, _ = _send(lambda: session.get(http_url(mprov_url) + "enroll/ca.crt",
                                            headers={"Authorization": None}, timeout=(10, 30)),
                        "Downloading the mPCC's CA certificate", log, sleep, resend_after_reply_lost=True)
    response.raise_for_status()
    ca_pem = response.text
    if pem_fingerprint(ca_pem) != ca_fp:
      log("Error: the mPCC's CA certificate doesn't match mprov_ca; not enrolling.")
      return False
    os.makedirs(tls_dir, mode=0o700, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=tls_dir) as tmp:
      ca_path = os.path.join(tmp, CA)
      _write(ca_path, ca_pem, 0o644)
      csr = make_csr(os.path.join(tmp, KEY))
      import requests
      try:
        # the nonce is redeemed and the CSR signed all or nothing, so a try
        # the mPCC refused for overload leaves the nonce usable.
        reply, maybe_used = _send(
          lambda: session.post(https_url(mprov_url) + "enroll/system/", data=json.dumps({"nonce": nonce, "csr": csr}),
                               headers={"Content-Type": "application/json", "Authorization": None},
                               verify=ca_path, timeout=(10, 30)),
          "Enrolling", log, sleep, resend_after_reply_lost=False)
      except requests.exceptions.ReadTimeout:
        # the mPCC may have used the nonce: sending it again would only be
        # refused, and logged there as a possible attack.
        log("Error: the mPCC didn't answer the enrollment in time, and may have used this boot's one-time "
            "nonce. Reboot the node to get a new one; using the shared API key.")
        return False
      if reply.status_code == 403 and maybe_used:
        log("Error: enrollment refused (403): this boot's one-time nonce was already used, most likely by this "
            "node's own earlier try, whose reply was lost. Reboot the node to get a new one; using the shared API key.")
        return False
      if reply.status_code != 200:
        log(f"Error: enrollment refused ({reply.status_code}): {reply.text[:200]}; using the shared API key.")
        return False
      _write(os.path.join(tmp, CERT), reply.json()["certificate"], 0o644)
      _write(os.path.join(tmp, URL), https_url(mprov_url) + "\n", 0o644)
      for name in (KEY, CERT, CA, URL):
        os.replace(os.path.join(tmp, name), os.path.join(tls_dir, name))
  except (OSError, ValueError, KeyError, subprocess.CalledProcessError, Exception) as e:
    log(f"Error: couldn't enroll ({e.__class__.__name__}: {e}); using the shared API key.")
    return False
  log(f"Enrolled with the mPCC; credential in {tls_dir}.")
  return True


def use(session, mprov_url, tls_dir=TLS_DIR):
  """ Point session at the mPCC over HTTPS with this node's credential, and
  return the HTTPS URL to use.  The shared API key is dropped. """
  session.cert = (os.path.join(tls_dir, CERT), os.path.join(tls_dir, KEY))
  session.verify = os.path.join(tls_dir, CA)
  session.headers.pop("Authorization", None)
  return https_url(mprov_url)


def valid_for(seconds, tls_dir=TLS_DIR):
  """ Whether the credential is still valid seconds from now (openssl x509
  -checkend). """
  result = subprocess.run(["openssl", "x509", "-noout", "-checkend", str(int(seconds)),
                           "-in", os.path.join(tls_dir, CERT)], capture_output=True, text=True)
  return result.returncode == 0


def _new_credential(session, url, tls_dir, log, what, **kwargs):
  """ POST a new CSR to url and swap in the key and certificate it returns.
  True on success. """
  with tempfile.TemporaryDirectory(dir=tls_dir) as tmp:
    csr = make_csr(os.path.join(tmp, KEY))
    reply = session.post(url, data=json.dumps({"csr": csr}), timeout=(10, 30),
                         headers={"Content-Type": "application/json", "Authorization": None},
                         verify=os.path.join(tls_dir, CA), **kwargs)
    if reply.status_code != 200:
      log(f"Error: {what} refused ({reply.status_code}): {reply.text[:300]}")
      return False
    _write(os.path.join(tmp, CERT), reply.json()["certificate"], 0o644)
    # the certificate first: a node stopped between the two renames has a
    # certificate its old key doesn't match, which a recovery window fixes;
    # the other way round it'd look valid and fail every handshake.
    os.replace(os.path.join(tmp, CERT), os.path.join(tls_dir, CERT))
    os.replace(os.path.join(tmp, KEY), os.path.join(tls_dir, KEY))
  return True


def renew(session=None, tls_dir=TLS_DIR, log=print, days=RENEW_DAYS):
  """ Keep this node's credential current.  True when it's current afterwards,
  or there's none to keep. """
  if not have(tls_dir) or not os.path.isfile(os.path.join(tls_dir, URL)):
    log("No credential to renew; this node uses the shared API key.")
    return True
  if valid_for(days * 86400, tls_dir):
    log("The credential isn't due for renewal.")
    return True
  if session is None:
    import requests
    session = requests.Session()
  with open(os.path.join(tls_dir, URL)) as f:
    base = f.read().strip()
  if valid_for(60, tls_dir):
    try:
      if _new_credential(session, base + "enroll/renew/", tls_dir, log, "renewal",
                         cert=(os.path.join(tls_dir, CERT), os.path.join(tls_dir, KEY))):
        log("Renewed the credential.")
        return True
    except Exception as e:
      log(f"Error: couldn't renew ({e.__class__.__name__}: {e}).")
  return recover(session, tls_dir, log)


def recover(session=None, tls_dir=TLS_DIR, log=print):
  """ Re-enroll through the window an admin opened for this system. """
  if session is None:
    import requests
    session = requests.Session()
  try:
    with open(os.path.join(tls_dir, URL)) as f:
      base = f.read().strip()
    if _new_credential(session, base + "enroll/recover/", tls_dir, log, "re-enrollment"):
      log("Re-enrolled; the credential is current again.")
      return True
  except Exception as e:
    log(f"Error: couldn't re-enroll ({e.__class__.__name__}: {e}).")
  log("The credential has expired or is about to. In the mPCC, select this system and use "
      "\"Let these systems re-enroll\"; this node picks it up on its next check or boot.")
  return False


def status(tls_dir=TLS_DIR, log=print):
  if not have(tls_dir):
    log("No credential; this node uses the shared API key.")
    return True
  result = subprocess.run(["openssl", "x509", "-noout", "-subject", "-enddate", "-in", os.path.join(tls_dir, CERT)],
                          capture_output=True, text=True)
  log(result.stdout.strip())
  log("valid" if valid_for(0, tls_dir) else "EXPIRED")
  return True


def main(argv=None):
  import sys
  args = sys.argv[1:] if argv is None else argv
  commands = {"renew": renew, "recover": recover, "status": status}
  if len(args) != 1 or args[0] not in commands:
    print(f"usage: mprov_enroll.py {{{'|'.join(commands)}}}")
    return 2
  return 0 if commands[args[0]]() else 1


if __name__ == "__main__":
  raise SystemExit(main())
