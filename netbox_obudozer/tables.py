"""
Таблицы для отображения данных в списках.
"""
import django_tables2 as tables
from netbox.tables import NetBoxTable, columns
from .models import ObuServices


class ObuServicesTable(NetBoxTable):
    """
    Таблица для отображения списка услуг OBU.

    NetBoxTable автоматически предоставляет:
    - Чекбоксы для выбора (если есть bulk actions)
    - Кнопки действий
    - Сортируемые колонки
    """

    name = tables.Column(
        linkify=True,  # Ссылка на detail view
        verbose_name='Название услуги'
    )

    tenant = tables.Column(
        linkify=True,
        verbose_name='Организация'
    )

    start_date = tables.DateColumn(
        verbose_name='Дата начала'
    )

    end_date = tables.DateColumn(
        verbose_name='Дата окончания'
    )

    description = tables.Column(
        verbose_name='Описание'
    )

    # Новая колонка для отображения количества VM
    vm_count = tables.Column(
        verbose_name='Количество VM',
        empty_values=(),
        orderable=False
    )

    # Унаследованные колонки из NetBoxModel:
    # - created (дата создания)
    # - last_updated (дата последнего изменения)

    class Meta(NetBoxTable.Meta):
        model = ObuServices
        fields = ('name', 'tenant', 'start_date', 'end_date', 'description', 'vm_count', 'created', 'last_updated')
        default_columns = ('name', 'tenant', 'start_date', 'end_date', 'vm_count')

    def render_vm_count(self, record):
        """Отображение количества назначенных VM."""
        return record.vm_assignments.count()
