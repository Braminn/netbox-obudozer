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

    vm_role = columns.ColoredLabelColumn(
        verbose_name='Роль сервиса'
    )

    description = tables.Column(
        verbose_name='Описание'
    )

    vm_count = tables.Column(
        verbose_name='Количество VM',
    )

    # Унаследованные колонки из NetBoxModel:
    # - created (дата создания)
    # - last_updated (дата последнего изменения)

    class Meta(NetBoxTable.Meta):
        model = ObuServices
        fields = ('name', 'vm_role', 'tenant', 'description', 'vm_count', 'created', 'last_updated')
        default_columns = ('name', 'vm_role', 'tenant', 'vm_count')

