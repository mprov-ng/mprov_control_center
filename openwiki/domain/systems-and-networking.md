---
type: Reference
title: Systems & Networking
description: How mProv Control Center models provisioned machines (System, NetworkInterface, SystemBMC, SystemImage) and networks (Network, Switch, SwitchPort), the signal-driven pxe/dns/dhcp job queueing, IPMI power control, and the network subnet-change confirmation flow.
tags: [mprov, systems, networks, ipmi, pxe, django-admin]
---

# Systems & Networking

These two apps hold the physical inventory: machines ([systems/](../../systems/)) and the L2/L3 topology they plug into ([networks/](../../networks/)). Their save/delete signals are the primary producers of jobs into the [Job Queue](jobs-and-scripts.md), which jobservers execute as pxe/dns/dhcp/image updates. All endpoints inherit [MProvView](../architecture/api-foundation.md) conventions, including `?detail` nested reads.

## Systems (`systems/`)

Key models (`systems/models.py`):

- **System** — a provisioned machine: `hostname`, `stateful` flag, FK to `SystemImage`, M2M to `DiskLayout` (see [OS & Disk Management](os-and-disk-management.md)), M2Ms to scripts/Ansible content, and a `config` dict built by `flatten_config()`. Config inheritance merges OSDistro → SystemGroup → System, where an `=`-prefixed value replaces the inherited list and an unprefixed value appends (kernel cmdline, module lists).
- **NetworkInterface** — belongs to a System, attaches one-to-one to a `SwitchPort`, carries `ipaddress`/MAC/bootable flags; IPv6 link-local/guarded-global addresses are computed alongside.
- **SystemBMC** — "Power Management" credentials per system (inline max 1; password field uses `PasswordInput` and is never exposed on flat API lists, only via `?detail`).
- **SystemImage** — the PXE-bootable image definition (slug PK, `version`, `needs_rebuild`, `customIPXE`).
- Plus `SystemGroup`, `SystemModel`, `SystemLocation`, and `NADSSystem` (switch-based auto-discovery: an NADS post_save copies the discovered MAC onto the system's bootable NIC).

**Signals are the behavior**: saving a System/NIC/BMC queues `pxe-update`, `dns-update`, `dhcp-update` jobs; saving a `SystemImage` bumps its version, clears assigned jobservers, and queues `image-update`; deleting an image queues per-server `image-delete`. These write into the [job queue](jobs-and-scripts.md) — mPCC never touches TFTP/DNS directly.

**Admin** (`systems/admin.py`): `SystemAdmin` embeds a `NetworkInterfaceInline` (custom `NetForm` widgets; a formset restricts `switch_port` choices to unassigned ports — the IP Address widget deliberately has no narrowing style, enforced by `systems/test_nic_inline.py`) and a `BMCInline`. IPMI power actions (`sys_on/off/cycle/pxe/pxe_efi`) use `pyipmi` plus raw `ipmitool` with the `IPMI_PASSWORD` env var. A `bulk_update` admin action (template `systems/templates/admin/system_bulk_change_form.html`) includes a `set_bootable` option, and a `_copy_to_new` button clones systems.

**API** (`systems/views.py`): `SystemAPIView` (own `get()` with `SystemDetailSerializer`), `SystemRegAPIView` at `/systems/register/` (unauthenticated NADS registration, derives IPv6 link-local from MAC), `SystemPowerAPIView` at `power/<action>/`, and the unauthenticated iPXE endpoint `views_noauth.py:IPXEAPIView` (see quickstart backlog for a full no-auth audit).

## Networks (`networks/`)

Key models (`networks/models.py`): `NetworkType`; `Network` (slug, VLAN, subnet/CIDR, gateway/nameservers, `isdhcp`/`managedns`/`isbootable`, DHCP range); `Switch` and `SwitchPort` (the OneToOne target NICs attach to). Signals queue pxe/dns/dhcp update jobs on save and delete-jobs on delete, same pattern as systems.

**Subnet-change confirmation flow** (`networks/admin.py`, `networks/api_views.py`, `networks/utils.py`): editing a Network's subnet/netmask in the admin does not save immediately. The edit is stashed in the session and the operator is redirected to `networks/<pk>/update-with-confirmation/`, which previews every affected NIC/BMC IP rebased into the new network (`calculate_new_ip(s)` preserves host bits and nulls collisions/network/broadcast addresses) before applying; `preview-subnet-changes` exposes the same preview as JSON. This exists because one bad subnet edit would silently invalidate an entire rack's addressing.

**API**: `NetworkAPIView`, `NetworkTypeAPIView`, `SwitchAPIView` (custom `?network=` slug filter), `SwitchPortAPIView`.

## Change guidance

- Anything that changes NIC/BMC/system fields: check `flatten_config()` inheritance semantics and the signal job payloads before editing.
- Admin form changes on the NIC inline: keep `systems/test_nic_inline.py` green (widget attributes are asserted exactly).
- Detail-serializer or security changes around BMC passwords: `systems/test_detail_serializer.py` asserts the flat list never exposes the BMC password.
- Key sources: `systems/{models,admin,views,views_noauth,serializers}.py`, `networks/{models,admin,api_views,utils}.py`.
