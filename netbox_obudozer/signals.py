"""
Django signals для автоматической синхронизации custom field obu_services и tenant.

Обработчики отслеживают изменения в ServiceVMAssignment и ObuServices,
автоматически обновляя:
- custom field 'obu_services' на связанных виртуальных машинах
- tenant на связанных виртуальных машинах
"""
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from .models import ServiceVMAssignment, ObuServices, OperatingSystem


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

    # Обновляем custom fields
    vm.custom_field_data['obu_services'] = service_ids
    vm.custom_field_data['has_obu_services'] = len(service_ids) > 0
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


@receiver(post_save, sender=ObuServices)
def recalc_problems_on_service_save(sender, instance, **kwargs):
    """
    Пересчитывает проблемы услуги (CF service_problems) сразу после её сохранения,
    чтобы на странице услуги после редактирования были видны актуальные проблемы.

    Рекурсии нет: recalc_service_problems() пишет через bulk_update(),
    который post_save не вызывает.
    """
    from .problems import recalc_service_problems, SERVICE_PROBLEMS_FIELD

    recalc_service_problems(ObuServices.objects.filter(pk=instance.pk))

    # Актуализируем и объект в памяти: если в этом же запросе его сохранят
    # ещё раз, старое значение не затрёт только что записанное.
    instance.custom_field_data[SERVICE_PROBLEMS_FIELD] = (
        ObuServices.objects.filter(pk=instance.pk)
        .values_list(f'custom_field_data__{SERVICE_PROBLEMS_FIELD}', flat=True)
        .first()
    )


@receiver([post_save, post_delete], sender=OperatingSystem)
def recalc_problems_on_os_change(sender, instance, **kwargs):
    """
    Пересчитывает проблемы ВМ с этой ОС (vm_os_eol / vm_os_eol_soon) после
    изменения или удаления записи реестра версий ОС — например, когда
    администратор проставил дату окончания поддержки. Следом каскадно
    пересчитываются услуги этих ВМ (наследуют проблемы ВМ).
    """
    from virtualization.models import VirtualMachine
    from .problems import recalc_vm_problems, VM_OS_FIELD

    recalc_vm_problems(
        VirtualMachine.objects.filter(**{f'custom_field_data__{VM_OS_FIELD}': instance.name})
    )


@receiver([post_save, post_delete], sender=ServiceVMAssignment)
def recalc_problems_on_assignment_change(sender, instance, **kwargs):
    """
    Пересчитывает проблемы услуги при привязке/отвязке ВМ: услуга наследует
    проблемы своих ВМ, поэтому набор ВМ влияет на service_problems.
    При каскадном удалении самой услуги фильтр просто ничего не найдёт.
    """
    from .problems import recalc_service_problems

    recalc_service_problems(ObuServices.objects.filter(pk=instance.service_id))


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

    # Получаем первую услугу с vm_role (если есть)
    first_service_with_role = (
        ServiceVMAssignment.objects
        .filter(virtual_machine=vm, service__vm_role__isnull=False)
        .select_related('service__vm_role')
        .first()
    )

    # Обновляем роль VM
    if first_service_with_role:
        vm.role = first_service_with_role.service.vm_role
    else:
        vm.role = None

    vm.save()
