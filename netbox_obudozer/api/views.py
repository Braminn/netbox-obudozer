"""
Views REST API для плагина netbox_obudozer

Определяет API endpoints для работы с VM Records.
"""
from netbox.api.viewsets import NetBoxModelViewSet
from ..models import VMRecord
from .serializers import VMRecordSerializer


class VMRecordViewSet(NetBoxModelViewSet):
    """
    API ViewSet для VMRecord.
    
    Предоставляет стандартные CRUD операции через REST API:
    - GET /api/plugins/obudozer/vm-records/ - список VM
    - POST /api/plugins/obudozer/vm-records/ - создание VM
    - GET /api/plugins/obudozer/vm-records/{id}/ - детали VM
    - PUT/PATCH /api/plugins/obudozer/vm-records/{id}/ - обновление VM
    - DELETE /api/plugins/obudozer/vm-records/{id}/ - удаление VM
    """
    queryset = VMRecord.objects.all()
    serializer_class = VMRecordSerializer
    
    # Фильтры для API
    filterset_fields = {
        'name': ['exact', 'icontains'],
        'state': ['exact'],
        'vcenter_id': ['exact', 'icontains'],
        'exist': ['exact'],
    }
