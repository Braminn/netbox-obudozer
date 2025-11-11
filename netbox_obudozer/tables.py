"""
Таблицы для отображения данных плагина netbox_obudozer

Определяет структуру таблиц для отображения VM Records в UI.
"""
import django_tables2 as tables
from netbox.tables import NetBoxTable, columns
from .models import VMRecord


class VMRecordTable(NetBoxTable):
    """
    Таблица для отображения VM Records.
    
    Отображает список виртуальных машин с возможностью сортировки и фильтрации.
    """
    
    name = tables.Column(
        linkify=True,
        verbose_name='Name'
    )
    
    state = columns.ChoiceFieldColumn(
        verbose_name='State'
    )
    
    vcenter_id = tables.Column(
        verbose_name='vCenter ID',
        empty_values=()
    )
    
    exist = columns.BooleanColumn(
        verbose_name='Exists in vCenter'
    )
    
    last_synced = columns.DateTimeColumn(
        verbose_name='Last Synced'
    )
    
    created = columns.DateTimeColumn(
        verbose_name='Created'
    )
    
    last_updated = columns.DateTimeColumn(
        verbose_name='Updated'
    )
    
    actions = columns.ActionsColumn(
        actions=('edit', 'delete')
    )

    class Meta(NetBoxTable.Meta):
        model = VMRecord
        fields = (
            'pk', 'id', 'name', 'state', 'vcenter_id', 'exist', 
            'last_synced', 'created', 'last_updated', 'actions'
        )
        default_columns = (
            'name', 'state', 'vcenter_id', 'exist', 'last_synced', 'actions'
        )

    def render_name(self, value, record):
        """
        Кастомный рендеринг имени VM с индикатором состояния.
        """
        if not record.exist:
            return f'⚠️ {value}'
        elif record.state == 'running':
            return f'▶️ {value}'
        else:
            return f'⏹️ {value}'
