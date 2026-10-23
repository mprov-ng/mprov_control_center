---
type: Reference
title: OS & Disk Management
description: How mProv Control Center manages OS distros and repositories (OSType, OSDistro auto-generated repos, OSRepo update jobs) and disk layouts (DiskLayout SCSI default, DiskPartition, RaidLayout software RAID) including the wizard-based admin flows.
tags: [mprov, osmanagement, disklayouts, repos, raid, provisioning]
---

# OS & Disk Management

These apps define *what* gets installed on a machine: the OS distro/repo sources ([osmanagement/](../../osmanagement/)) and the partition/RAID layout ([disklayouts/](../../disklayouts/)). Both feed [Systems](systems-and-networking.md) — a `System` inherits config from its `OSDistro` and references `DiskLayout` rows — and both enqueue work into the [Job Queue](jobs-and-scripts.md) when their content changes.

## OS management (`osmanagement/`)

Models (`osmanagement/models.py`): `OSType`; `OSDistro` (architecture choices, `baseurl`, `baserepo`/`osrepos`/`extrarepos`, root password/SSH keys, and the inheritable config fields merged into `System.flatten_config()`); `OSRepo` (mirror `repo_package_url`, `managed`/`update` flags, `hosted_by` JobServers, local mirror `version`). Note: "OS images" in mPCC terms are `SystemImage` in the systems app, not here; there is no package-level modeling.

Notable automation:

- **Auto-generated repos**: an `OSDistro` post_save creates AppStream/BaseOS/extras (plus CRB for EL ≥9, else PowerTools) and EPEL `OSRepo` rows from the distro `baseurl`, guarded by a self-relief flag to avoid recursion.
- **Repo mirroring**: saving an `OSRepo` with `update=True` bumps its version, clears `hosted_by`, and queues `repo-update` jobs; deleting a JobServer requeues repo-updates for every repo it hosted. The admin `mark_update` action (managed repos only) bumps the version with a queryset `.update()` to avoid double increments.
- Endpoints: `distros/`, `repos/`, `ostypes/`, `osrepos/` route modules (`osmanagement/*_urls.py`); an unauthenticated `views_noauth.py` exists (see quickstart backlog).

## Disk layouts (`disklayouts/`)

Models (`disklayouts/models.py`): `DiskLayout` (slug PK, `dtype` of SCSI / NVMe / Software-RAID, M2M back to Systems); `DiskPartition` (partnum, mount point, size MB, `fill`, `format`, bootable); `RaidLayout` (multi-table-inheritance child of DiskLayout with `raidlevel`, `partition_members`, mount).

**dtype default fix (issue #271)**: when the RAID default was once changed, it silently became the default for *all* new layouts. Now `DiskLayout.dtype` defaults to SCSI at both the field and instance level (migration `0028_disklayout_dtype_default_scsi.py`), and `RaidLayout.__init__` applies `kwargs.setdefault('dtype', MDRD)` only when constructed without positional args, so rows loaded from the DB keep their stored dtype. `disklayouts/test_dtype_default.py` pins all of this, including that dtype-less rows still appear in the admin.

**Wizard admin**: both `DiskLayoutAdmin` and `RaidLayoutAdmin` use `AdminWizardModel` from `common/admin.py` (multi-step creation wizard). `DiskLayoutAdmin.get_queryset` excludes software-RAID rows from the plain layout list, and the wizard's first step removes "Software RAID" from the dtype choices — RAID layouts are created and listed separately via `RaidLayoutAdmin`, which limits `partition_members` to partitions marked `mount=filesystem="raid"`. `disklayouts/notes.txt` holds informal device-naming design notes.

## Change guidance

- Any `disklayouts` model change must keep the SCSI-default invariant and pass `disklayouts/test_dtype_default.py`; new migrations for default changes need care because existing rows must retain stored values.
- Changing `OSDistro.baseurl` semantics ripples into auto-generated repos and `repo-update` job payloads in the [job queue](jobs-and-scripts.md).
- Remember config inheritance order OSDistro → SystemGroup → System with `=`-prefix override semantics (documented in [Systems & Networking](systems-and-networking.md)).
- Key sources: `osmanagement/{models,admin,forms}.py`, `disklayouts/{models,admin}.py`, `disklayouts/migrations/0028_disklayout_dtype_default_scsi.py`, `common/admin.py`.
