"""
API Views (ViewSets) для плагина netbox_obudozer

Определяет REST API endpoints для моделей плагина.
"""
from django.db.models import Count
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet
from netbox.api.viewsets import NetBoxModelViewSet
from ..models import ObuServices, ServiceVMAssignment, NginxDomain, OperatingSystem
from ..rutoken import get_outsourcing_contacts
from .serializers import (
    ObuServicesSerializer,
    ServiceVMAssignmentSerializer,
    NginxDomainSerializer,
    OperatingSystemSerializer,
    RutokenAccessSerializer,
)


class RutokenAccessListView(APIView):
    """
    Endpoint для внешних bash-скриптов: контакты арендаторов группы outsourcing.

    Сбор данных — в rutoken.py, здесь только отдача. Требует API-токена NetBox
    (Authorization: Token <token>), как и остальные endpoints плагина.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        contacts = get_outsourcing_contacts()
        return Response({
            'rutoken_access_list': RutokenAccessSerializer(contacts, many=True).data
        })


class ServiceVMAssignmentViewSet(ModelViewSet):
    """
    ViewSet для ServiceVMAssignment.

    ВАЖНО: Используем ModelViewSet (НЕ NetBoxModelViewSet), т.к.
    ServiceVMAssignment не наследует от NetBoxModel.
    """
    queryset = ServiceVMAssignment.objects.select_related('service', 'virtual_machine')
    serializer_class = ServiceVMAssignmentSerializer


class NginxDomainViewSet(NetBoxModelViewSet):
    queryset = NginxDomain.objects.all()
    serializer_class = NginxDomainSerializer


class OperatingSystemViewSet(NetBoxModelViewSet):
    queryset = OperatingSystem.objects.all()
    serializer_class = OperatingSystemSerializer


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
