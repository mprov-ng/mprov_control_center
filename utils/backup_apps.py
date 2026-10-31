# App/model labels dumped by `mprov_backup` and restored by `mprov_restore`,
# in dependency order.
#
# `systems` and `disklayouts` have a genuine cross-app M2M cycle
# (systems.System.disks <-> disklayouts.DiskLayout.systems, the same
# through table accessed from both sides), so no linear order satisfies
# both directions. This is fine in practice: Django's `loaddata` disables
# FK constraint checking for every fixture file passed to a single
# invocation and only checks them once everything has loaded, so
# `mprov_restore` loads every file from a backup in one `loaddata` call
# rather than one call per app. The order below is kept sensible anyway,
# for readability of the numbered fixture files and in case anyone loads
# them individually.
BACKUP_LABELS = [
    "auth.User",
    "auth.Group",
    "rest_framework_api_key",
    "scripts",
    "networks",
    "jobqueue",
    "osmanagement",
    "disklayouts",
    "systems",
]

MANIFEST_NAME = "manifest.json"
