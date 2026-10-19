import ipaddress
from django.db.models import Q
from .models import Network
from systems.models import SystemBMC, NetworkInterface


def calculate_new_ip(old_ip, old_network, new_network):
    """
    Calculate the new IP address for old_ip when its network changes from
    old_network to new_network: the new network's address plus the old
    address's low bits, as many bits as the new netmask leaves for hosts.

    So the same-size move 10.0.1.5 (10.0.1.0/24) -> 10.0.2.0/24 gives
    10.0.2.5, and growing 172.16.1.5 (172.16.1.0/24) -> 10.1.0.0/16 gives
    10.1.1.5.  Works for any netmask, IPv4 or IPv6.  When the new network is
    smaller, different addresses can map to the same one; calculate_new_ips()
    checks a whole network's addresses for that.

    Args:
        old_ip (str): Original IP address
        old_network (Network): Original network object (not used; kept so
            callers don't change)
        new_network (Network): New network object

    Returns:
        str: New IP address in the new subnet, or None if it would be the
        new network's network or broadcast address, or an error occurred
    """
    try:
        old_ip_obj = ipaddress.ip_address(old_ip)
        new_net = ipaddress.ip_network(f"{new_network.subnet}/{int(new_network.netmask)}", strict=False)

        # the old address's bits that the new netmask leaves for hosts.
        host = int(old_ip_obj) & int(new_net.hostmask)
        new_ip = new_net.network_address + host
        if new_net.version == 4 and new_net.prefixlen < 31 and new_ip in (new_net.network_address, new_net.broadcast_address):
            print(f"Error calculating new IP: {old_ip} maps to {new_ip}, the network or broadcast address of {new_net}")
            return None
        return str(new_ip)

    except Exception as e:
        print(f"Error calculating new IP: {e}")
        import traceback
        traceback.print_exc()
        return None


def calculate_new_ips(old_ips, old_network, new_network):
    """
    Calculate new IP addresses for all of a network's addresses at once (see
    calculate_new_ip).  An address that would end up the same as another
    one's (possible when the new network is smaller) gets None, so it's
    reported and left alone instead of silently duplicated.

    Returns:
        dict: old IP (str) -> new IP (str), or None if it couldn't be moved
    """
    new_ips = {ip: calculate_new_ip(ip, old_network, new_network) for ip in set(old_ips) if ip}
    taken = {}
    for ip, new_ip in new_ips.items():
        if new_ip is not None:
            taken.setdefault(new_ip, []).append(ip)
    for new_ip, ips in taken.items():
        if len(ips) > 1:
            print(f"Error calculating new IP: {', '.join(sorted(ips))} would all become {new_ip}")
            for ip in ips:
                new_ips[ip] = None
    return new_ips


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
    # NICs and BMCs share the network's address space, so map them together.
    new_ips = calculate_new_ips([i.ipaddress for i in associated['interfaces']] + [b.ipaddress for b in associated['bmcs']], old_network, network)
    
    results = {
        'interfaces_updated': 0,
        'bmcs_updated': 0,
        'errors': []
    }
    
    # Update network interfaces
    for interface in associated['interfaces']:
        if interface.ipaddress:
            new_ip = new_ips.get(interface.ipaddress)
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
            new_ip = new_ips.get(bmc.ipaddress)
            if new_ip:
                old_ip = bmc.ipaddress
                bmc.ipaddress = new_ip
                bmc.save()
                results['bmcs_updated'] += 1
                print(f"Updated BMC for {bmc.system.hostname}: {old_ip} -> {new_ip}")
            else:
                results['errors'].append(f"Failed to calculate new IP for BMC on {bmc.system.hostname}")
    
    return results
