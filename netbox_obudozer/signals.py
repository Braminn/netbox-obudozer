"""
Django signals для автоматической синхронизации custom field obu_services и tenant.

Обработчики отслеживают изменения в ServiceVMAssignment и ObuServices,
автоматически обновляя:
- custom field 'obu_services' на связанных виртуальных машинах
- tenant на связанных виртуальных машинах
"""
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from .models import ServiceVMAssignment, ObuServices


@receiver([post_save, post_delete], sender=ServiceVMAssignment)
def sync_vm_services_custom_field(sender, instance, **kwargs):
    """
    Синхронизирует custom field 'obu_services' при изменении assignments.

    Обрабатывает:
    - post_save: Создание или изменение assignment
    - post_delete: Удаление assignment

    Args:
        sender: Класс модели (ServiceVMAssignment)
        instance: Экземпляр ServiceVMAssignment
        **kwargs: Дополнительные параметры сигнала
    """
    vm = instance.virtual_machine

    # Получаем актуальный список ID всех сервисов для данной VM
    service_ids = list(
        ServiceVMAssignment.objects
        .filter(virtual_machine=vm)
        .values_list('service_id', flat=True)
        .order_by('service_id')  # Сортировка для стабильности
    )

    # Обновляем custom field
    vm.custom_field_data['obu_services'] = service_ids
    vm.save()


@receiver(post_save, sender=ObuServices)
def sync_tenant_to_vms(sender, instance, created, **kwargs):
    """
    Синхронизирует tenant от услуги ко всем привязанным VM.

    Когда у услуги изменяется tenant, автоматически проставляет
    этот же tenant всем виртуальным машинам, привязанным к услуге.

    Args:
        sender: Класс модели (ObuServices)
        instance: Экземпляр ObuServices
        created: True если объект только что создан
        **kwargs: Дополнительные параметры сигнала
    """
    # Получаем все VM, привязанные к этой услуге
    from virtualization.models import VirtualMachine

    vm_ids = instance.vm_assignments.values_list('virtual_machine_id', flat=True)

    # Обновляем tenant у каждой VM
    # Используем явное сохранение для каждой VM, чтобы:
    # - Создавались записи в истории изменений (ObjectChange)
    # - Срабатывали другие сигналы и валидация
    for vm in VirtualMachine.objects.filter(id__in=vm_ids):
        vm.tenant = instance.tenant
        vm.save()


@receiver([post_save, post_delete], sender=ServiceVMAssignment)
def sync_tenant_on_assignment_change(sender, instance, **kwargs):
    """
    Синхронизирует tenant при изменении привязки VM к услуге.

    Когда VM добавляется к услуге - проставляет tenant от услуги.
    Когда VM удаляется из всех услуг - очищает tenant.

    Args:
        sender: Класс модели (ServiceVMAssignment)
        instance: Экземпляр ServiceVMAssignment
        **kwargs: Дополнительные параметры сигнала
    """
    vm = instance.virtual_machine

    # Получаем первую услугу с tenant (если есть)
    first_service_with_tenant = (
        ServiceVMAssignment.objects
        .filter(virtual_machine=vm, service__tenant__isnull=False)
        .select_related('service__tenant')
        .first()
    )

    # Обновляем tenant VM
    if first_service_with_tenant:
        vm.tenant = first_service_with_tenant.service.tenant
    else:
        vm.tenant = None

    vm.save()
