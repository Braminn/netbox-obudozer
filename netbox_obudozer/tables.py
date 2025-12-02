import django_tables2 as tables
from netbox.tables import NetBoxTable, columns
from .models import BusinessService, ServiceVMAssignment


class BusinessServiceTable(NetBoxTable):
    """
    Таблица для отображения списка бизнес-сервисов.
    """
    name = tables.Column(
        linkify=True,
        verbose_name='Название'
    )

    organization = tables.Column(
        linkify=True,
        verbose_name='Организация'
    )

    status = columns.ChoiceFieldColumn(
        verbose_name='Статус'
    )

    responsible_person = tables.Column(
        verbose_name='Ответственное лицо'
    )

    contract_start_date = tables.DateColumn(
        format='d.m.Y',
        verbose_name='Начало договора'
    )

    contract_end_date = tables.DateColumn(
        format='d.m.Y',
        verbose_name='Окончание договора'
    )

    request_number = tables.Column(
        verbose_name='№ заявки'
    )

    vm_count = columns.ManyToManyColumn(
        accessor='vm_assignments',
        verbose_name='VM',
        orderable=False
    )

    tags = columns.TagColumn(
        url_name='plugins:netbox_obudozer:businessservice_list'
    )

    comments = columns.MarkdownColumn(
        verbose_name='Комментарии'
    )

    class Meta(NetBoxTable.Meta):
        model = BusinessService
        fields = (
            'pk', 'id', 'name', 'organization', 'status', 'responsible_person',
            'contract_start_date', 'contract_end_date', 'request_number',
            'vm_count', 'tags', 'created', 'last_updated', 'comments', 'actions'
        )
        default_columns = (
            'pk', 'name', 'organization', 'status', 'responsible_person',
            'contract_start_date', 'contract_end_date', 'vm_count'
        )


class ServiceVMAssignmentTable(NetBoxTable):
    """
    Таблица для отображения привязок VM к сервисам.
    """
    service = tables.Column(
        linkify=True,
        verbose_name='Сервис'
    )

    virtual_machine = tables.Column(
        linkify=True,
        verbose_name='VM'
    )

    assigned_date = tables.DateColumn(
        format='d.m.Y',
        verbose_name='Дата назначения'
    )

    notes = columns.MarkdownColumn(
        verbose_name='Примечания'
    )

    actions = columns.ActionsColumn(
        actions=('delete',)
    )

    class Meta(NetBoxTable.Meta):
        model = ServiceVMAssignment
        fields = ('pk', 'id', 'service', 'virtual_machine', 'assigned_date', 'notes', 'actions')
        default_columns = ('pk', 'service', 'virtual_machine', 'assigned_date', 'actions')
