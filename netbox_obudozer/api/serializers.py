"""
API сериализаторы для netbox_obudozer
"""
from rest_framework import serializers
from netbox.api.serializers import NetBoxModelSerializer
from tenancy.api.serializers import TenantSerializer
from virtualization.api.serializers import VirtualMachineSerializer
from ..models import BusinessService, ServiceVMAssignment


class BusinessServiceSerializer(NetBoxModelSerializer):
    """
    Сериализатор для модели BusinessService.
    """
    organization = TenantSerializer(nested=True)

    class Meta:
        model = BusinessService
        fields = [
            'id', 'url', 'display', 'name', 'organization', 'status',
            'contract_start_date', 'contract_end_date', 'request_number',
            'responsible_person', 'description', 'tags', 'custom_fields',
            'created', 'last_updated'
        ]
        brief_fields = ['id', 'url', 'display', 'name']


class ServiceVMAssignmentSerializer(serializers.ModelSerializer):
    """
    Сериализатор для модели ServiceVMAssignment.
    """
    service = BusinessServiceSerializer(nested=True, read_only=True)
    virtual_machine = VirtualMachineSerializer(nested=True, read_only=True)

    class Meta:
        model = ServiceVMAssignment
        fields = [
            'id', 'service', 'virtual_machine', 'assigned_date', 'notes'
        ]
