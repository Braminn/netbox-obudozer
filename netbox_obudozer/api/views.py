"""
API views для netbox_obudozer
"""
from netbox.api.viewsets import NetBoxModelViewSet
from rest_framework.viewsets import ReadOnlyModelViewSet
from ..models import BusinessService, ServiceVMAssignment
from .serializers import BusinessServiceSerializer, ServiceVMAssignmentSerializer


class BusinessServiceViewSet(NetBoxModelViewSet):
    """
    API ViewSet для BusinessService.
    """
    queryset = BusinessService.objects.prefetch_related('tags', 'organization')
    serializer_class = BusinessServiceSerializer


class ServiceVMAssignmentViewSet(ReadOnlyModelViewSet):
    """
    API ViewSet для ServiceVMAssignment (read-only).
    """
    queryset = ServiceVMAssignment.objects.select_related('service', 'virtual_machine')
    serializer_class = ServiceVMAssignmentSerializer
