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
from .serializers import ObuServicesSerializer, ServiceVMAssignmentSerializer, NginxDomainSerializer, OperatingSystemSerializer


class RutokenAccessListView(APIView):
    """
    Тестовый endpoint для проверки подключения внешних bash-скриптов к API плагина.

    Пока отдаёт фиксированные данные-заглушку. Требует API-токена NetBox
    (Authorization: Token <token>), как и остальные endpoints плагина.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        data = {
            'rutoken_access_list': [
                {'id': 1, 'rutoken_cert': 'protolabnewext_1764176618637_rutokenVpnClient'},
                {'id': 2, 'rutoken_cert': 'barscentrext_1707723385824_rutokenVpnClient'},
            ]
        }
        return Response(data)


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
