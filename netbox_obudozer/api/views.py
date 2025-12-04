"""
API Views (ViewSets) для плагина netbox_obudozer

Определяет REST API endpoints для моделей плагина.
"""
from netbox.api.viewsets import NetBoxModelViewSet
from ..models import ObuServices
from .serializers import ObuServicesSerializer


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
    queryset = ObuServices.objects.all()
    serializer_class = ObuServicesSerializer
