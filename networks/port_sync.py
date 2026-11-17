""" Keep a switch port's network and its NIC's network the same (#578), for
saves a person or an API client makes: in the admin, or through the API with
a user's session or token.

- A port saved with a new network puts its NIC on that network.
- A NIC saved with a new network, or linked to another port, puts its port
  on the NIC's network.

Only a change to the saved side's network (or a NIC's port) syncs, so an
unrelated edit never overwrites the other side.  A cleared network (None)
isn't copied: clearing a port's network would take its NIC out of DNS and
DHCP.  BMCs aren't synced.

A node's own saves (its certificate, or the shared key in nodes mode) are
left out: NetworkInterfaceSerializer has its own, narrower rule for them
(#575).  So are saves outside a request (jobs, management commands).

The other side is saved with update_fields, so its own signals run (a NIC's
queues the dnsmasq jobs), and its sync back is a no-op since the networks
already match. """
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from common.permissions import node_system
from common.request import get_current_request
from jobqueue.models import changes_fields
from networks.models import SwitchPort
from systems.models import NetworkInterface


def _syncs():
  """ Whether saves now are a person's or an API client's, not a node's. """
  request = get_current_request()
  return request is not None and node_system(request) is None


@receiver(pre_save, sender=SwitchPort)
def note_port_network_change(sender, instance, update_fields=None, raw=False, **kwargs):
  instance._network_changed = not raw and _syncs() and changes_fields(instance, ('networks',), update_fields)


@receiver(post_save, sender=SwitchPort)
def port_network_to_nic(sender, instance, **kwargs):
  if not getattr(instance, '_network_changed', False) or instance.networks_id is None:
    return
  nic = NetworkInterface.objects.filter(switch_port=instance).first()
  if nic is not None and nic.network_id != instance.networks_id:
    nic.network_id = instance.networks_id
    nic.save(update_fields=['network'])


@receiver(pre_save, sender=NetworkInterface)
def note_nic_network_change(sender, instance, update_fields=None, raw=False, **kwargs):
  instance._network_changed = not raw and _syncs() and changes_fields(instance, ('network', 'switch_port'),
                                                                      update_fields)


@receiver(post_save, sender=NetworkInterface)
def nic_network_to_port(sender, instance, **kwargs):
  if not getattr(instance, '_network_changed', False):
    return
  if instance.network_id is None or instance.switch_port_id is None:
    return
  port = SwitchPort.objects.filter(pk=instance.switch_port_id).first()
  if port is not None and port.networks_id != instance.network_id:
    port.networks_id = instance.network_id
    port.save(update_fields=['networks'])
