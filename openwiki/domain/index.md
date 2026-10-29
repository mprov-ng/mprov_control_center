---
type: Documentation Index
title: "Domain"
description: "Files and subdirectories in Domain."
---

# Files

- [Jobs & Scripts](jobs-and-scripts.md) - The mProv Control Center job queue (Job, JobModule, JobServer heartbeat registration, job polling API, live status polling) and the scripts app (Script content-on-disk storage, version handling, Ansible playbooks/roles/collections).
- [OS & Disk Management](os-and-disk-management.md) - How mProv Control Center manages OS distros and repositories (OSType, OSDistro auto-generated repos, one-shot OSRepo resync jobs) and disk layouts (DiskLayout SCSI default, DiskPartition, RaidLayout software RAID) including the wizard-based admin flows and the boot-disk warning for stateful systems.
- [Systems & Networking](systems-and-networking.md) - How mProv Control Center models provisioned machines (System, NetworkInterface, SystemBMC, SystemImage) and networks (Network, Switch, SwitchPort), the render_config() config inheritance merge (distro, groups, image, system) served on /systems/ and /systemimages/, the provision flag and PXE Boot gating, the signal-driven pxe/dns/dhcp job queueing, IPMI power control, the admin Rendered Config and Network Summary tabs, and the network subnet-change confirmation flow.
