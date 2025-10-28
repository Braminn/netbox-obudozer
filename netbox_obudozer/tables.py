import django_tables2 as tables
from netbox.tables import NetBoxTable, columns
from .models import VMRecord


class VMRecordTable(NetBoxTable):
    """Таблица для отображения VM записей"""

    name = tables.Column(
        linkify=True,
        verbose_name='Name'
    )

    state = columns.ChoiceFieldColumn(
        verbose_name='State'
    )

    created = columns.DateTimeColumn(
        verbose_name='Created'
    )

    updated = columns.DateTimeColumn(
        verbose_name='Updated'
    )

    actions = columns.ActionsColumn(
        actions=('edit', 'delete')
    )

    class Meta(NetBoxTable.Meta):
        model = VMRecord
        fields = ('pk', 'id', 'name', 'state', 'created', 'updated', 'actions')
        default_columns = ('name', 'state', 'created', 'updated', 'actions')
