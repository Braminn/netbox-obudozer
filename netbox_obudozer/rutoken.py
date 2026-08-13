"""
Сбор данных для Rutoken Access API (`/api/plugins/obudozer/rutoken-access/`).

Логика вынесена из api/views.py: view остаётся тонким, весь сбор и дальнейшая
обработка данных живут здесь.

Цепочка связей в NetBox (контакт НЕ привязан к арендатору напрямую):

    TenantGroup (slug 'outsourcing')
      └─ Tenant.group                       ← отсев по графику работы (work_time)
           └─ ContactAssignment (generic FK: object_type=Tenant, object_id=tenant.pk)
                └─ Contact                  ← rutoken_cert из custom field

Модуль спроектирован так, чтобы не падать при отсутствии данных: нет группы,
нет арендаторов, нет контактов, никто не работает — возвращается пустой список.
"""
import logging

from django.contrib.contenttypes.models import ContentType
from django.db.models import Q
from django.utils import timezone
from tenancy.models import ContactAssignment, Tenant, TenantGroup

from .work_time import is_working_now

logger = logging.getLogger('netbox.plugins.netbox_obudozer.rutoken')

# Группа арендаторов, контакты которых попадают в выдачу.
# Пока захардкожено; при необходимости выносится в PLUGINS_CONFIG.
OUTSOURCING_GROUP_SLUG = 'outsourcing'

# Custom field на tenancy.Contact с идентификатором Rutoken-сертификата.
# Создаётся в фазе подготовки синхронизации (custom_fields.py), заполняется вручную.
RUTOKEN_CERT_FIELD = 'rutoken_cert'

# Custom field на tenancy.Tenant с графиком работы арендатора (текст).
# Создан вручную в NetBox, плагин его только читает.
WORK_TIME_FIELD = 'work_time'

# Попадают ли в выдачу арендаторы с пустым/неразобранным графиком работы.
# По умолчанию нет: нет графика — нет доступа.
INCLUDE_TENANTS_WITHOUT_WORK_TIME = False


def _get_group_ids(slug=OUTSOURCING_GROUP_SLUG):
    """
    ID группы арендаторов + всех вложенных подгрупп.

    Обход дерева идёт по parent_id, а не через API дерева (mptt/tree-queries) —
    так не зависим от того, на чём именно построены вложенные группы в текущей
    версии NetBox.

    :return: список ID; пустой список, если группа не найдена.
    """
    root_ids = set(
        TenantGroup.objects.filter(
            Q(slug__icontains=slug) | Q(name__icontains=slug)
        ).values_list('pk', flat=True)
    )
    if not root_ids:
        logger.warning("Группа арендаторов '%s' не найдена — выдача будет пустой", slug)
        return []

    all_ids = set(root_ids)
    frontier = root_ids
    while frontier:
        frontier = set(
            TenantGroup.objects
            .filter(parent_id__in=frontier)
            .exclude(pk__in=all_ids)
            .values_list('pk', flat=True)
        )
        all_ids |= frontier

    return list(all_ids)


def _get_open_tenants(group_ids, now=None):
    """
    Арендаторы из указанных групп, у которых СЕЙЧАС рабочее время.

    График берётся из текстового custom field `work_time` арендатора
    (например «ПН-ЧТ: 8:30-17:30, ПТ: 8:30-16:30»), разбор — в work_time.py.

    Арендатор НЕ попадает в результат, если поле пустое, отсутствует или
    формат не распознан: без графика считаем, что права на выдачу нет.
    Чтобы включать таких арендаторов, см. INCLUDE_TENANTS_WITHOUT_WORK_TIME.

    :return: {tenant_id: tenant_name} только по «открытым» сейчас арендаторам
    """
    # Момент проверки фиксируем один раз, чтобы все арендаторы сравнивались
    # с одним и тем же временем
    now = now or timezone.localtime()

    open_tenants = {}
    for pk, name, cf_data in Tenant.objects.filter(
        group_id__in=group_ids
    ).values_list('pk', 'name', 'custom_field_data'):
        schedule = str((cf_data or {}).get(WORK_TIME_FIELD) or '')

        if not schedule.strip():
            if INCLUDE_TENANTS_WITHOUT_WORK_TIME:
                open_tenants[pk] = name
            else:
                logger.debug("Арендатор %r без графика работы — пропускаем", name)
            continue

        if is_working_now(schedule, now=now):
            open_tenants[pk] = name

    if not open_tenants:
        logger.info('Нет арендаторов, работающих в текущее время — выдача пустая')

    return open_tenants


def get_outsourcing_contacts():
    """
    Контакты арендаторов группы outsourcing, работающих в текущее время.

    Арендаторы вне своего графика работы (custom field work_time) в выдачу
    не попадают вместе со своими контактами.

    Один контакт может быть привязан к нескольким арендаторам — тогда он
    попадает в результат несколько раз, по записи на каждого арендатора
    (это нужно для дальнейшей логики). Дубли по одной и той же паре
    (контакт, арендатор) — например, когда контакт привязан к арендатору
    с разными ролями — схлопываются.

    rutoken_cert берётся из одноимённого custom field контакта
    (создаётся в custom_fields.ensure_contact_custom_fields).

    :return: список dict с ключами id / name / org / rutoken_cert
    """
    group_ids = _get_group_ids()
    if not group_ids:
        return []

    tenant_names = _get_open_tenants(group_ids)
    if not tenant_names:
        return []

    assignments = (
        ContactAssignment.objects
        .filter(
            object_type=ContentType.objects.get_for_model(Tenant),
            object_id__in=tenant_names.keys(),
        )
        .select_related('contact')
        .order_by('contact__name', 'object_id')
    )

    result = []
    seen = set()
    for assignment in assignments:
        key = (assignment.contact_id, assignment.object_id)
        if key in seen:
            continue
        seen.add(key)
        result.append({
            'id': assignment.contact_id,
            'name': assignment.contact.name,
            'org': tenant_names[assignment.object_id],
            # Поле может быть не заполнено или ещё не создано у контакта — тогда пустая строка
            'rutoken_cert': assignment.contact.custom_field_data.get(RUTOKEN_CERT_FIELD) or '',
        })

    return result
