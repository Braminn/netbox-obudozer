"""
API Views (ViewSets) для плагина netbox_obudozer

Определяет REST API endpoints для моделей плагина.
"""
from django.db.models import Count
from rest_framework.viewsets import ModelViewSet
from netbox.api.viewsets import NetBoxModelViewSet
from ..models import ObuServices, ServiceVMAssignment
from .serializers import ObuServicesSerializer, ServiceVMAssignmentSerializer


class ServiceVMAssignmentViewSet(ModelViewSet):
    """
    ViewSet для ServiceVMAssignment.

    ВАЖНО: Используем ModelViewSet (НЕ NetBoxModelViewSet), т.к.
    ServiceVMAssignment не наследует от NetBoxModel.
    """
    queryset = ServiceVMAssignment.objects.select_related('service', 'virtual_machine')
    serializer_class = ServiceVMAssignmentSerializer


class ObuServicesViewSet(NetBoxModelViewSet):
    """
    ViewSet для REST API модели ObuServices.

    Предоставляет стандартные CRUD операции:
    - GET /api/plugins/netbox-obudozer/obu-services/ - список всех услуг
    - POST /api/plugins/netbox-obudozer/obu-services/ - создание услуги
    - GET /api/plugins/netbox-obudozer/obu-services/{id}/ - детали услуги
    - PUT/PATCH /api/plugins/netbox-obudozer/obu-services/{id}/ - обновление услуги
    - DELETE /api/plugins/netbox-obudozer/obu-services/{id}/ - удаление услуги

    NetBoxModelViewSet автоматически обрабатывает:
    - Пагинацию
    - Фильтрацию (если определен filterset)
    - Bulk операции
    - Permissions
    """
    queryset = ObuServices.objects.annotate(
        vm_count=Count('vm_assignments')
    )
    serializer_class = ObuServicesSerializer
