"""
API сериализаторы для плагина netbox_obudozer

Определяет сериализаторы для REST API и внутреннего использования NetBox.
"""
from rest_framework import serializers
from netbox.api.serializers import NetBoxModelSerializer
from ..models import ObuServices


class ObuServicesSerializer(NetBoxModelSerializer):
    """
    Сериализатор для модели ObuServices.

    Используется как для REST API, так и для внутренних операций NetBox (например, форм).
    NetBoxModelSerializer автоматически обрабатывает:
    - Поля url, display, id
    - Теги (tags)
    - Пользовательские поля (custom_fields)
    - Временные метки (created, last_updated)
    """

    url = serializers.HyperlinkedIdentityField(
        view_name='plugins-api:netbox_obudozer-api:obuservices-detail'
    )

    class Meta:
        model = ObuServices
        fields = (
            'id', 'url', 'display', 'name', 'description',
            'tags', 'custom_fields', 'created', 'last_updated',
        )
        brief_fields = ('id', 'url', 'display', 'name')
