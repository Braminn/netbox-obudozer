"""
API сериализаторы для плагина netbox_obudozer

Определяет сериализаторы для REST API и внутреннего использования NetBox.
"""
from rest_framework import serializers
from netbox.api.serializers import NetBoxModelSerializer
from virtualization.models import VirtualMachine
from ..models import ObuServices, ServiceVMAssignment


class ServiceVMAssignmentSerializer(serializers.ModelSerializer):
    """
    Сериализатор для промежуточной модели ServiceVMAssignment.

    ВАЖНО: НЕ наследует от NetBoxModelSerializer, т.к. ServiceVMAssignment
    не является NetBoxModel (это обычная промежуточная модель).
    """

    url = serializers.HyperlinkedIdentityField(
        view_name='plugins-api:netbox_obudozer-api:servicevmassignment-detail'
    )

    # Вложенные объекты для чтения
    service = serializers.SerializerMethodField()
    virtual_machine = serializers.SerializerMethodField()

    # ID для записи
    service_id = serializers.PrimaryKeyRelatedField(
        queryset=ObuServices.objects.all(),
        source='service',
        write_only=True
    )
    virtual_machine_id = serializers.PrimaryKeyRelatedField(
        queryset=VirtualMachine.objects.all(),
        source='virtual_machine',
        write_only=True
    )

    class Meta:
        model = ServiceVMAssignment
        fields = (
            'id', 'url', 'display',
            'service', 'service_id',
            'virtual_machine', 'virtual_machine_id',
            'notes',
        )

    def get_service(self, obj):
        return {'id': obj.service.id, 'name': obj.service.name, 'url': obj.service.get_absolute_url()}

    def get_virtual_machine(self, obj):
        return {'id': obj.virtual_machine.id, 'name': obj.virtual_machine.name}


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

    # Добавить поле vm_count (будет аннотировано в ViewSet)
    vm_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = ObuServices
        fields = (
            'id', 'url', 'display', 'name', 'description',
            'vm_count',  # Новое поле
            'tags', 'custom_fields', 'created', 'last_updated',
        )
        brief_fields = ('id', 'url', 'display', 'name')
