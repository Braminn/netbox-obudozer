from netbox.api.viewsets import NetBoxModelViewSet
from ..models import VMRecord
from .serializers import VMRecordSerializer


class VMRecordViewSet(NetBoxModelViewSet):
    queryset = VMRecord.objects.all()
    serializer_class = VMRecordSerializer
