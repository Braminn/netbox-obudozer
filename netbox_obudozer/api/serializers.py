from rest_framework import serializers
from netbox.api.serializers import NetBoxModelSerializer
from ..models import VMRecord


class VMRecordSerializer(NetBoxModelSerializer):
    """Сериализатор для VMRecord"""

    url = serializers.HyperlinkedIdentityField(
        view_name='plugins-api:netbox_obudozer-api:vmrecord-detail'
    )

    class Meta:
        model = VMRecord
        fields = ('id', 'url', 'display', 'name', 'state', 'created', 'last_updated', 'tags', 'custom_fields')
