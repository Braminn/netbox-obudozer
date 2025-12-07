"""
API модуль плагина netbox_obudozer

Экспортирует сериализаторы и ViewSet'ы для использования NetBox.
"""
from .serializers import ObuServicesSerializer, ServiceVMAssignmentSerializer
from .views import ObuServicesViewSet, ServiceVMAssignmentViewSet

__all__ = [
    'ObuServicesSerializer',
    'ServiceVMAssignmentSerializer',
    'ObuServicesViewSet',
    'ServiceVMAssignmentViewSet',
]
