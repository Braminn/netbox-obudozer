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
        linkify=False,  # Пока нет detail view, не делаем ссылку
        verbose_name='Название услуги'
    )

    description = tables.Column(
        verbose_name='Описание'
    )

    # Унаследованные колонки из NetBoxModel:
    # - created (дата создания)
    # - last_updated (дата последнего изменения)

    class Meta(NetBoxTable.Meta):
        model = ObuServices
        fields = ('name', 'description', 'created', 'last_updated')
        default_columns = ('name', 'description')
