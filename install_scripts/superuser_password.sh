# Resolve the first-run superuser password (#317).  Sourced by
# init_mpcc.sh before the superuser is created; never run directly.
#
# Precedence:
#   1. MPROV_SUPERUSER_PASSWORD from the container env -- operator
#      override (e.g. set by mprov-compose); nothing is saved in that case.
#   2. The password saved by an earlier first run, at
#      $MPROV_ETC_DIR/superuser_password (default /etc/mprov, a root-only
#      volume that survives restarts and image updates).
#   3. A freshly generated random password, written only to that
#      root-only file (never to the world-readable .env) and printed once
#      so it lands in the container log for the installing operator.
#
# Everything here is shell-safe by construction: the generated token is
# URL-safe base64 ([A-Za-z0-9_-]), and both are quoted.
MPROV_ETC_DIR="${MPROV_ETC_DIR:-/etc/mprov}"
MPROV_SUPERUSER_PASSWORD_FILE="$MPROV_ETC_DIR/superuser_password"
if [ -n "${MPROV_SUPERUSER_PASSWORD:-}" ]; then
    : # the operator provided one; use it as-is
elif [ -s "$MPROV_SUPERUSER_PASSWORD_FILE" ]; then
    MPROV_SUPERUSER_PASSWORD=$(cat "$MPROV_SUPERUSER_PASSWORD_FILE")
else
    MPROV_SUPERUSER_PASSWORD=$(python3 -c 'import secrets; print(secrets.token_urlsafe(24))')
    mkdir -p "$MPROV_ETC_DIR"
    (umask 077; printf '%s\n' "$MPROV_SUPERUSER_PASSWORD" > "$MPROV_SUPERUSER_PASSWORD_FILE")
    chmod 600 "$MPROV_SUPERUSER_PASSWORD_FILE"
    echo "Generated a random superuser password for user '${DJANGO_SUPERUSER_USERNAME:-admin}', shown once here and saved to $MPROV_SUPERUSER_PASSWORD_FILE (root-only):" >&2
    echo "$MPROV_SUPERUSER_PASSWORD" >&2
fi
export MPROV_SUPERUSER_PASSWORD
