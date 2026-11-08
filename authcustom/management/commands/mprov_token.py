""" Make, list and revoke people's API tokens (#502), for scripted setups. """
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from authcustom.models import UserToken


class Command(BaseCommand):
    help = "Make (prints the token once), list or revoke a user's API tokens."

    def add_arguments(self, parser):
        sub = parser.add_subparsers(dest="action", required=True)
        create = sub.add_parser("create", help="Make a token and print it.")
        create.add_argument("--user", required=True)
        create.add_argument("--name", required=True)
        create.add_argument("--days", type=int, help="Days until it expires (default: never).")
        listing = sub.add_parser("list", help="List tokens (never their secrets).")
        listing.add_argument("--user")
        revoke = sub.add_parser("revoke", help="Revoke a token by its prefix.")
        revoke.add_argument("prefix")

    def handle(self, *args, **options):
        if options["action"] == "create":
            try:
                user = get_user_model().objects.get(username=options["user"])
            except get_user_model().DoesNotExist:
                raise CommandError(f"No user {options['user']!r}.")
            if not (user.is_active and user.is_staff):
                raise CommandError(f"{user.username} isn't an active staff user; tokens are for staff.")
            if options["days"] is not None and not 0 < options["days"] <= 3650:
                raise CommandError("--days must be from 1 to 3650.")
            _, secret = UserToken.make(user, options["name"], options["days"])
            self.stdout.write(secret)
        elif options["action"] == "list":
            tokens = UserToken.objects.select_related("user")
            if options["user"]:
                tokens = tokens.filter(user__username=options["user"])
            for t in tokens:
                state = "revoked" if t.revoked else ("expired" if t.has_expired else "active")
                self.stdout.write(f"{t.prefix}\t{t.user.username}\t{t.name}\t{state}\t"
                                  f"expires {t.expiry_date or 'never'}\tlast used {t.last_used or 'never'}")
        else:
            token = UserToken.objects.filter(prefix=options["prefix"]).first()
            if token is None:
                raise CommandError(f"No token with prefix {options['prefix']!r}.")
            token.revoked = True
            token.save(update_fields=["revoked"])
            self.stdout.write(f"Revoked {token}.")
