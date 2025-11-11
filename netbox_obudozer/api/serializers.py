"""
Сериализаторы REST API для плагина netbox_obudozer

Определяет как модели преобразуются в JSON для API.
"""
from rest_framework import serializers
from netbox.api.serializers import NetBoxModelSerializer
from ..models import VMRecord


class VMRecordSerializer(NetBoxModelSerializer):
    """
    Сериализатор для модели VMRecord.
    
    Преобразует объекты VMRecord в JSON и обратно для REST API.
    """
    
    url = serializers.HyperlinkedIdentityField(
        view_name='plugins-api:netbox_obudozer-api:vmrecord-detail'
    )
    
    state_display = serializers.CharField(
        source='get_state_display',
        read_only=True
    )
    
    status_display = serializers.SerializerMethodField()
    
    def get_status_display(self, obj):
        """Возвращает человекочитаемый статус VM"""
        return obj.status_display
    
    class Meta:
        model = VMRecord
        fields = (
            'id', 'url', 'display', 'name', 'state', 'state_display',
            'vcenter_id', 'exist', 'status_display', 'last_synced',
            'created', 'last_updated', 'tags', 'custom_fields'
        )
        read_only_fields = ('last_synced', 'created', 'last_updated')
