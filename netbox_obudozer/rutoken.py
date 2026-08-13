"""
Сбор данных для Rutoken Access API (`/api/plugins/obudozer/rutoken-access/`).

Логика вынесена из api/views.py: view остаётся тонким, весь сбор и дальнейшая
обработка данных живут здесь.

Цепочка связей в NetBox (контакт НЕ привязан к арендатору напрямую):

    TenantGroup (slug 'outsourcing')
      └─ Tenant.group
           └─ ContactAssignment (generic FK: object_type=Tenant, object_id=tenant.pk)
                └─ Contact

Модуль спроектирован так, чтобы не падать при отсутствии данных: нет группы,
нет арендаторов, нет контактов — возвращается пустой список.
"""
import logging

from django.contrib.contenttypes.models import ContentType
from django.db.models import Q
from tenancy.models import ContactAssignment, Tenant, TenantGroup

logger = logging.getLogger('netbox.plugins.netbox_obudozer.rutoken')

# Группа арендаторов, контакты которых попадают в выдачу.
# Пока захардкожено; при необходимости выносится в PLUGINS_CONFIG.
OUTSOURCING_GROUP_SLUG = 'outsourcing'


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


def get_outsourcing_contacts():
    """
    Контакты, привязанные к арендаторам группы outsourcing.

    Один контакт может быть привязан к нескольким арендаторам — тогда он
    попадает в результат несколько раз, по записи на каждого арендатора
    (это нужно для дальнейшей логики). Дубли по одной и той же паре
    (контакт, арендатор) — например, когда контакт привязан к арендатору
    с разными ролями — схлопываются.

    :return: список dict с ключами id / name / org / rutoken_cert
    """
    group_ids = _get_group_ids()
    if not group_ids:
        return []

    # {tenant_id: tenant_name} — чтобы не разрешать generic FK построчно (N+1)
    tenant_names = dict(
        Tenant.objects.filter(group_id__in=group_ids).values_list('pk', 'name')
    )
    if not tenant_names:
        logger.warning('В группе outsourcing нет арендаторов — выдача будет пустой')
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
            # Заполняется на следующем этапе
            'rutoken_cert': '',
        })

    return result
