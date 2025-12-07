"""
Django signals для автоматической синхронизации custom field obu_services.

Обработчики отслеживают изменения в ServiceVMAssignment и автоматически
обновляют custom field 'obu_services' на связанных виртуальных машинах.
"""
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from .models import ServiceVMAssignment


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
