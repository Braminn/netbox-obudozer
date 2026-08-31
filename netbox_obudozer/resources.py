"""
Подсчёт суммарных ресурсов виртуальных машин.

Одна и та же агрегация нужна на странице арендатора (template_extensions),
на странице услуги и на дашборде, поэтому вынесена сюда.

Учитываются только ВМ в статусе active — выключенные и недоступные (failed)
ресурсы фактически не потребляют.
"""
from django.db.models import Sum


def format_memory(mb):
    """memory хранится в бинарных МБ (1 ГБ = 1024 МБ)."""
    if mb >= 1024 * 1024:
        return f"{mb / 1024 / 1024:.1f} ТБ"
    if mb >= 1024:
        return f"{mb / 1024:.1f} ГБ"
    return f"{mb} МБ"


def format_disk(mb):
    """VirtualDisk.size хранится в десятичных МБ (1 ГБ = 1000 МБ, как в vCenter UI)."""
    if mb >= 1000 * 1000:
        return f"{mb / 1000 / 1000:.1f} ТБ"
    if mb >= 1000:
        return f"{mb / 1000:.1f} ГБ"
    return f"{mb} МБ"


def vm_resources(vms):
    """
    Суммарные ресурсы активных ВМ из переданного queryset.

    Args:
        vms: queryset VirtualMachine (фильтр по статусу применяется внутри)

    Returns:
        dict с ключами total_vcpus (int), total_memory (str), total_disk (str) —
        готов к передаче в шаблон.
    """
    from virtualization.models import VirtualDisk

    active_vms = vms.filter(status='active')
    active_vm_ids = list(active_vms.values_list('id', flat=True))

    totals = active_vms.aggregate(
        total_vcpus=Sum('vcpus'),
        total_memory=Sum('memory'),
    )
    disk_sum = VirtualDisk.objects.filter(
        virtual_machine_id__in=active_vm_ids
    ).aggregate(total=Sum('size'))

    return {
        'total_vcpus': int(totals['total_vcpus'] or 0),
        'total_memory': format_memory(totals['total_memory'] or 0),
        'total_disk': format_disk(disk_sum['total'] or 0),
    }
