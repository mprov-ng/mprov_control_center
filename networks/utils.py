import ipaddress
from django.db.models import Q
from .models import Network
from systems.models import SystemBMC, NetworkInterface


def calculate_new_ip(old_ip, old_network, new_network):
    """
    Calculate the new IP address for old_ip when its network changes from
    old_network to new_network, keeping its host part: the address's offset
    within the old network is applied to the new network's address.  Works
    for any netmask, IPv4 or IPv6.

    Args:
        old_ip (str): Original IP address
        old_network (Network): Original network object
        new_network (Network): New network object

    Returns:
        str: New IP address in the new subnet, or None if the host part
        doesn't fit in the new network or an error occurred
    """
    try:
        old_ip_obj = ipaddress.ip_address(old_ip)
        old_net = ipaddress.ip_network(f"{old_network.subnet}/{int(old_network.netmask)}", strict=False)
        new_net = ipaddress.ip_network(f"{new_network.subnet}/{int(new_network.netmask)}", strict=False)

        # the host bits of the old address, under the old netmask.
        host = int(old_ip_obj) & int(old_net.hostmask)
        if host >= new_net.num_addresses:
            # the new network is too small for this host; don't guess an
            # address that may already be in use.
            print(f"Error calculating new IP: {old_ip} has no matching address in {new_net}")
            return None
        return str(new_net.network_address + host)

    except Exception as e:
        print(f"Error calculating new IP: {e}")
        import traceback
        traceback.print_exc()
        return None


def get_associated_objects(network):
    """
    Get all network interfaces and BMCs associated with a network.

    Args:
        network (Network): Network object

    Returns:
        dict: Dictionary with 'interfaces' and 'bmcs' QuerySets
    """
    # Get network interfaces associated with this network
    interfaces = NetworkInterface.objects.filter(network=network).select_related('system')
    
    # Get BMCs associated with this network
    bmcs = SystemBMC.objects.filter(network=network).select_related('system')
    
    return {
        'interfaces': interfaces,
        'bmcs': bmcs
    }


def update_associated_ips(network, old_subnet, old_netmask):
    """
    Update IP addresses of all associated network interfaces and BMCs when the network changes.
    
    Args:
        network (Network): Updated network object
        old_subnet (str): Original subnet
        old_netmask (int): Original netmask
    
    Returns:
        dict: Results of the update operation
    """
    # Create old network object for reference
    old_network = Network(subnet=old_subnet, netmask=old_netmask)
    
    # Get associated objects
    associated = get_associated_objects(network)
    
    results = {
        'interfaces_updated': 0,
        'bmcs_updated': 0,
        'errors': []
    }
    
    # Update network interfaces
    for interface in associated['interfaces']:
        if interface.ipaddress:
            new_ip = calculate_new_ip(interface.ipaddress, old_network, network)
            if new_ip:
                old_ip = interface.ipaddress
                interface.ipaddress = new_ip
                interface.save()
                results['interfaces_updated'] += 1
                print(f"Updated interface {interface.name} for {interface.system.hostname}: {old_ip} -> {new_ip}")
            else:
                results['errors'].append(f"Failed to calculate new IP for interface {interface.name} on {interface.system.hostname}")
    
    # Update BMCs
    for bmc in associated['bmcs']:
        if bmc.ipaddress:
            new_ip = calculate_new_ip(bmc.ipaddress, old_network, network)
            if new_ip:
                old_ip = bmc.ipaddress
                bmc.ipaddress = new_ip
                bmc.save()
                results['bmcs_updated'] += 1
                print(f"Updated BMC for {bmc.system.hostname}: {old_ip} -> {new_ip}")
            else:
                results['errors'].append(f"Failed to calculate new IP for BMC on {bmc.system.hostname}")
    
    return results
