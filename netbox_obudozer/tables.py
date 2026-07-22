"""
Таблицы для отображения данных в списках.
"""
import django_tables2 as tables
from netbox.tables import NetBoxTable, columns
from .models import ObuServices, NginxDomain, OperatingSystem


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


class NginxDomainTable(NetBoxTable):
    domain = tables.TemplateColumn(
        verbose_name='Домен',
        order_by='domain',
        template_code="""
<a href="{{ record.get_absolute_url }}">{{ record.domain }}</a>
{% if record.domain_unicode %}<br><small class="text-muted">{{ record.domain_unicode }}</small>{% endif %}
""",
    )
    nginx_status = tables.TemplateColumn(
        verbose_name='Статус',
        orderable=False,
        template_code="""
{% with s=record.custom_field_data.nginx_status %}
{% if s == 'direct' %}<span class="badge bg-success">IP</span>
{% elif s == 'chained' %}<span class="badge bg-success">Цепочка</span>
{% elif s == 'upstream' %}<span class="badge bg-warning text-dark">Upstream</span>
{% elif s == 'loop' %}<span class="badge bg-info text-white">Петля</span>
{% elif s == 'unresolved' %}<span class="badge bg-danger">Не разрешён</span>
{% else %}<span class="badge bg-secondary">—</span>{% endif %}
{% endwith %}
""",
    )
    nginx_is_waf = tables.TemplateColumn(
        verbose_name='WAF',
        orderable=False,
        template_code="""
{% if record.custom_field_data.nginx_is_waf %}
<span class="badge bg-success"><i class="mdi mdi-shield-check"></i> WAF</span>
{% else %}—{% endif %}
""",
    )
    last_updated = tables.DateTimeColumn(verbose_name='Обновлено')

    class Meta(NetBoxTable.Meta):
        model = NginxDomain
        fields = ('domain', 'nginx_status', 'nginx_is_waf', 'last_updated', 'actions')
        default_columns = ('domain', 'nginx_status', 'nginx_is_waf', 'last_updated')


class OperatingSystemTable(NetBoxTable):
    name = tables.Column(linkify=True, verbose_name='Версия ОС')
    eol_date = tables.DateColumn(verbose_name='Дата окончания поддержки')
    eol_status = tables.TemplateColumn(
        verbose_name='Статус',
        orderable=False,
        template_code="""
{% if record.eol_status == 'expired' %}<span class="badge bg-danger">Просрочено</span>
{% elif record.eol_status == 'soon' %}<span class="badge bg-warning text-dark">Скоро истекает</span>
{% elif record.eol_status == 'ok' %}<span class="badge bg-success">OK</span>
{% else %}<span class="badge bg-secondary">Дата не задана</span>{% endif %}
""",
    )
    vm_count = tables.Column(verbose_name='Количество VM', orderable=False)

    class Meta(NetBoxTable.Meta):
        model = OperatingSystem
        fields = ('name', 'eol_date', 'eol_status', 'vm_count', 'created', 'last_updated')
        default_columns = ('name', 'eol_date', 'eol_status', 'vm_count')

