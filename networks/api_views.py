from rest_framework.response import Response
from rest_framework import status
from rest_framework.decorators import api_view
from django.shortcuts import get_object_or_404
from .models import Network
from .utils import get_associated_objects, update_associated_ips
from .serializers import NetworkAPISerializer
import json


@api_view(['POST'])
def update_network_with_confirmation(request, pk):
    """
    Update a network with confirmation for subnet changes.
    
    This endpoint allows updating a network and prompts for confirmation
    when the subnet is changed, offering to update associated systems and BMCs.
    
    POST /networks/{pk}/update-with-confirmation/
    
    Request body:
    {
        "network_data": {
            "name": "Network Name",
            "subnet": "192.168.1.0",
            "netmask": 24,
            "gateway": "192.168.1.1",
            ...
        },
        "update_associated": true/false  // Only required for confirmation step
    }
    
    Response formats:
    
    1. If subnet changed and update_associated not provided:
    {
        "requires_confirmation": true,
        "message": "Subnet is changing. Do you want to update associated systems and BMCs?",
        "associated_objects": {
            "interfaces": [
                {
                    "id": 1,
                    "name": "eth0",
                    "system": "hostname1",
                    "current_ip": "192.168.0.10",
                    "proposed_ip": "192.168.1.10"
                }
            ],
            "bmcs": [
                {
                    "id": 1,
                    "system": "hostname1",
                    "current_ip": "192.168.0.11",
                    "proposed_ip": "192.168.1.11"
                }
            ]
        }
    }
    
    2. If update successful:
    {
        "success": true,
        "message": "Network updated successfully",
        "updated_network": {...},
        "update_results": {
            "interfaces_updated": 5,
            "bmcs_updated": 3,
            "errors": []
        }
    }
    """
    
    network = get_object_or_404(Network, pk=pk)
    
    try:
        data = json.loads(request.body)
        network_data = data.get('network_data', {})
        update_associated = data.get('update_associated', None)
    except (json.JSONDecodeError, KeyError):
        return Response(
            {"error": "Invalid JSON data"}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Check if subnet is changing
    old_subnet = str(network.subnet)
    old_netmask = network.netmask
    new_subnet = network_data.get('subnet', old_subnet)
    new_netmask = network_data.get('netmask', old_netmask)
    
    subnet_changing = (old_subnet != new_subnet or old_netmask != new_netmask)
    
    # If subnet is changing and no confirmation provided, show what will be updated
    if subnet_changing and update_associated is None:
        # Get associated objects and calculate proposed new IPs
        associated = get_associated_objects(network)
        
        # Create a temporary network object for IP calculation
        temp_network = Network(subnet=new_subnet, netmask=new_netmask)
        old_network = Network(subnet=old_subnet, netmask=old_netmask)
        
        from .utils import calculate_new_ip
        
        proposed_interfaces = []
        for interface in associated['interfaces']:
            if interface.ipaddress:
                proposed_ip = calculate_new_ip(interface.ipaddress, old_network, temp_network)
                if proposed_ip:
                    proposed_interfaces.append({
                        'id': interface.id,
                        'name': interface.name,
                        'system': interface.system.hostname,
                        'current_ip': interface.ipaddress,
                        'proposed_ip': proposed_ip
                    })
        
        proposed_bmcs = []
        for bmc in associated['bmcs']:
            if bmc.ipaddress:
                proposed_ip = calculate_new_ip(bmc.ipaddress, old_network, temp_network)
                if proposed_ip:
                    proposed_bmcs.append({
                        'id': bmc.id,
                        'system': bmc.system.hostname,
                        'current_ip': bmc.ipaddress,
                        'proposed_ip': proposed_ip
                    })
        
        return Response({
            'requires_confirmation': True,
            'message': 'Subnet is changing. Do you want to update associated systems and BMCs?',
            'old_subnet': f"{old_subnet}/{old_netmask}",
            'new_subnet': f"{new_subnet}/{new_netmask}",
            'associated_objects': {
                'interfaces': proposed_interfaces,
                'bmcs': proposed_bmcs
            }
        })
    
    # Update the network
    serializer = NetworkAPISerializer(network, data=network_data, partial=True)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    # Save the network
    network = serializer.save()
    
    # If subnet changed and user confirmed, update associated objects
    update_results = None
    if subnet_changing and update_associated:
        update_results = update_associated_ips(network, old_subnet, old_netmask)
    
    response_data = {
        'success': True,
        'message': 'Network updated successfully',
        'updated_network': serializer.data
    }
    
    if update_results:
        response_data['update_results'] = update_results
    
    return Response(response_data, status=status.HTTP_200_OK)


@api_view(['GET'])
def preview_subnet_changes(request, pk):
    """
    Preview what IP changes would occur if the network subnet changes.
    
    GET /networks/{pk}/preview-subnet-changes/?new_subnet=192.168.1.0&new_netmask=24
    
    Response:
    {
        "old_subnet": "192.168.0.0/24",
        "new_subnet": "192.168.1.0/24",
        "proposed_changes": {
            "interfaces": [...],
            "bmcs": [...]
        }
    }
    """
    
    network = get_object_or_404(Network, pk=pk)
    
    new_subnet = request.query_params.get('new_subnet')
    new_netmask = request.query_params.get('new_netmask')
    
    if not new_subnet or not new_netmask:
        return Response(
            {"error": "new_subnet and new_netmask parameters are required"}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        new_netmask = int(new_netmask)
    except ValueError:
        return Response(
            {"error": "new_netmask must be an integer"}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Get associated objects and calculate proposed new IPs
    associated = get_associated_objects(network)
    
    # Create temporary network objects for IP calculation
    temp_network = Network(subnet=new_subnet, netmask=new_netmask)
    old_network = Network(subnet=network.subnet, netmask=network.netmask)
    
    from .utils import calculate_new_ip
    
    proposed_interfaces = []
    for interface in associated['interfaces']:
        if interface.ipaddress:
            proposed_ip = calculate_new_ip(interface.ipaddress, old_network, temp_network)
            if proposed_ip:
                proposed_interfaces.append({
                    'id': interface.id,
                    'name': interface.name,
                    'system': interface.system.hostname,
                    'current_ip': interface.ipaddress,
                    'proposed_ip': proposed_ip
                })
    
    proposed_bmcs = []
    for bmc in associated['bmcs']:
        if bmc.ipaddress:
            proposed_ip = calculate_new_ip(bmc.ipaddress, old_network, temp_network)
            if proposed_ip:
                proposed_bmcs.append({
                    'id': bmc.id,
                    'system': bmc.system.hostname,
                    'current_ip': bmc.ipaddress,
                    'proposed_ip': proposed_ip
                })
    
    return Response({
        'old_subnet': f"{network.subnet}/{network.netmask}",
        'new_subnet': f"{new_subnet}/{new_netmask}",
        'proposed_changes': {
            'interfaces': proposed_interfaces,
            'bmcs': proposed_bmcs
        }
    })
