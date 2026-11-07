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
"""
import base64
import hashlib
import json
import os
import re
import subprocess
import tempfile
from urllib.parse import urlsplit, urlunsplit

TLS_DIR = "/etc/mprov/tls"
KEY, CERT, CA = "node.key", "node.crt", "ca.crt"


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


def enroll(session, mprov_url, cmdline="/proc/cmdline", tls_dir=TLS_DIR, log=print):
  """ Enroll this boot, if it was given a nonce.  True when the node has its
  credential in tls_dir afterwards. """
  nonce, ca_fp = kernel_params(cmdline)
  if nonce is None or ca_fp is None:
    log("No enrollment parameters on the kernel command line; using the shared API key.")
    return False
  try:
    # no API key: this download isn't an agent's API call
    response = session.get(mprov_url.rstrip("/") + "/enroll/ca.crt", headers={"Authorization": None},
                           timeout=(10, 30))
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
      reply = session.post(https_url(mprov_url) + "enroll/system/", data=json.dumps({"nonce": nonce, "csr": csr}),
                           headers={"Content-Type": "application/json", "Authorization": None},
                           verify=ca_path, timeout=(10, 30))
      if reply.status_code != 200:
        log(f"Error: enrollment refused ({reply.status_code}): {reply.text[:200]}; using the shared API key.")
        return False
      _write(os.path.join(tmp, CERT), reply.json()["certificate"], 0o644)
      for name in (KEY, CERT, CA):
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
