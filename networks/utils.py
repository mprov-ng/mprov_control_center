import ipaddress
from django.db.models import Q
from .models import Network
from systems.models import SystemBMC, NetworkInterface


def calculate_new_ip(old_ip, old_network, new_network):
    """
    Calculate the new IP address by replacing only the network portion
    while keeping the host portion the same.
    
    Args:
        old_ip (str): Original IP address
        old_network (Network): Original network object
        new_network (Network): New network object
    
    Returns:
        str: New IP address in the new subnet
    """
    try:
        # Parse the old IP address
        old_ip_obj = ipaddress.IPv4Address(old_ip)
        old_ip_parts = str(old_ip_obj).split('.')
        
        # Parse the new network to get the new network octets
        new_net = ipaddress.IPv4Network(f"{new_network.subnet}/{new_network.netmask}", strict=False)
        new_net_parts = str(new_net.network_address).split('.')
        
        # Determine how many octets are part of the network based on netmask
        netmask = new_network.netmask
        if netmask >= 24:
            # /24 networks - first 3 octets are network
            network_octets = 3
        elif netmask >= 16:
            # /16 networks - first 2 octets are network
            network_octets = 2
        elif netmask >= 8:
            # /8 networks - first octet is network
            network_octets = 1
        else:
            # /0 or invalid - treat as no network octets
            network_octets = 0
        
        # Build the new IP by combining new network octets with old host octets
        if network_octets > 0:
            new_ip_parts = new_net_parts[:network_octets] + old_ip_parts[network_octets:]
        else:
            # If no network octets, just use the old IP
            new_ip_parts = old_ip_parts
        
        new_ip = '.'.join(new_ip_parts)
        
        # Validate the new IP is within the new network
        new_ip_obj = ipaddress.IPv4Address(new_ip)
        if new_ip_obj not in new_net:
            # If the calculated IP is not in the new network, 
            # use the first available IP in the new network
            new_ip_obj = list(new_net.hosts())[0] if list(new_net.hosts()) else new_net.network_address + 1
            new_ip = str(new_ip_obj)
        
        return new_ip
        
    except Exception as e:
        print(f"Error calculating new IP: {e}")
        import traceback
        traceback.print_exc()
        return None


def get_associated_objects(network):
    """
    Get all systems and BMCs associated with a network.
    
    Args:
        network (Network): Network object
    
    Returns:
        dict: Dictionary with 'interfaces' and 'bmcs' lists
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
    Update IP addresses of all associated systems and BMCs when network changes.
    
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
