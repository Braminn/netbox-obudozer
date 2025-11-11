"""
Модуль синхронизации данных между vCenter и NetBox

Реализует 3-фазный подход синхронизации:
1. Preparation - получение и подготовка данных
2. Diff - вычисление различий
3. Apply - применение изменений

Использует встроенный NetBox механизм логирования изменений через ObjectChange.
"""
from typing import Dict, List, Tuple
from django.db import transaction
from django.utils import timezone
from django.contrib.contenttypes.models import ContentType
from virtualization.models import ClusterType, Cluster, VirtualMachine
from extras.models import CustomField

from .models import VMRecord
from .vmware import get_vcenter_vms, test_vcenter_connection, cluster_info


class SyncResult:
    """
    Результат выполнения синхронизации.
    
    Хранит статистику о выполненных операциях.
    
    Attributes:
        created (int): Количество созданных VM
        updated (int): Количество обновленных VM
        unchanged (int): Количество неизмененных VM
        marked_missing (int): Количество VM помеченных как отсутствующие
        errors (List[str]): Список ошибок, возникших при синхронизации
        total_processed (int): Общее количество обработанных VM
        duration (float): Длительность синхронизации в секундах
    """
    
    def __init__(self):
        self.created = 0
        self.updated = 0
        self.unchanged = 0
        self.marked_missing = 0
        self.errors = []
        self.total_processed = 0
        self.duration = 0.0
        self.start_time = None
        self.end_time = None
    
    def start(self):
        """Отмечает начало синхронизации"""
        self.start_time = timezone.now()
    
    def finish(self):
        """Отмечает завершение синхронизации и вычисляет длительность"""
        self.end_time = timezone.now()
        if self.start_time:
            self.duration = (self.end_time - self.start_time).total_seconds()
    
    def __str__(self):
        """Строковое представление результата"""
        # Гарантируем что duration - это число
        duration_seconds = float(self.duration) if self.duration else 0.0
        return (
            f"Синхронизация завершена за {duration_seconds:.2f} сек:\n"
            f"  Создано: {self.created}\n"
            f"  Обновлено: {self.updated}\n"
            f"  Без изменений: {self.unchanged}\n"
            f"  Помечено отсутствующими: {self.marked_missing}\n"
            f"  Ошибок: {len(self.errors)}\n"
            f"  Всего обработано: {self.total_processed}"
        )


class VMDiff:
    """
    Вычисление различий между данными vCenter и NetBox.
    
    Attributes:
        to_create: VM которые нужно создать
        to_update: VM которые нужно обновить (VM, изменения)
        to_skip: VM без изменений
        to_mark_missing: VM которые нужно пометить как отсутствующие
    """
    
    def __init__(self):
        self.to_create: List[Dict] = []
        self.to_update: List[Tuple[VMRecord, Dict]] = []
        self.to_skip: List[VMRecord] = []
        self.to_mark_missing: List[VMRecord] = []


def get_field_changes(vm_record: VMRecord, vcenter_data: Dict) -> Dict:
    """
    Определяет какие поля изменились.
    
    Args:
        vm_record: Существующая запись VM в NetBox
        vcenter_data: Новые данные из vCenter
    
    Returns:
        Dict с измененными полями: {'field_name': {'old': old_value, 'new': new_value}}
    
    Example:
        >>> changes = get_field_changes(vm, {'state': 'running'})
        >>> print(changes)
        {'state': {'old': 'stopped', 'new': 'running'}}
    """
    changes = {}
    
    # Проверяем state
    if vm_record.state != vcenter_data['state']:
        changes['state'] = {
            'old': vm_record.state,
            'new': vcenter_data['state']
        }
    
    # Проверяем vcenter_id (может измениться при пересоздании VM)
    vcenter_id = vcenter_data.get('vcenter_id')
    if vcenter_id and vm_record.vcenter_id != vcenter_id:
        changes['vcenter_id'] = {
            'old': vm_record.vcenter_id,
            'new': vcenter_id
        }
    
    # Если VM была помечена как отсутствующая, но теперь найдена
    if not vm_record.exist:
        changes['exist'] = {
            'old': False,
            'new': True
        }
    
    return changes


def calculate_diff(vcenter_vms: List[Dict], existing_vms: Dict[str, VMRecord]) -> VMDiff:
    """
    ФАЗА 2: Вычисляет различия между vCenter и NetBox.
    
    Args:
        vcenter_vms: Список VM из vCenter
        existing_vms: Словарь существующих VM в NetBox (name -> VMRecord)
    
    Returns:
        VMDiff объект с информацией о необходимых изменениях
    """
    diff = VMDiff()
    vcenter_names = set()
    
    # Проходим по всем VM из vCenter
    for vm_data in vcenter_vms:
        vm_name = vm_data['name']
        vcenter_names.add(vm_name)
        
        if vm_name in existing_vms:
            # VM существует - проверяем изменения
            vm_record = existing_vms[vm_name]
            changes = get_field_changes(vm_record, vm_data)
            
            if changes:
                diff.to_update.append((vm_record, changes))
            else:
                diff.to_skip.append(vm_record)
        else:
            # VM не существует - нужно создать
            diff.to_create.append(vm_data)
    
    # Находим VM которых нет в vCenter
    for vm_name, vm_record in existing_vms.items():
        if vm_name not in vcenter_names and vm_record.exist:
            diff.to_mark_missing.append(vm_record)
    
    return diff


@transaction.atomic
def apply_changes(diff: VMDiff, result: SyncResult) -> SyncResult:
    """
    ФАЗА 3: Применяет изменения к базе данных.
    
    Выполняется в транзакции для обеспечения целостности данных.
    
    Args:
        diff: Объект с вычисленными различиями
        result: Объект для сохранения результатов
    
    Returns:
        Обновленный SyncResult
    """
    sync_time = timezone.now()
    
    # Создание новых VM
    for vm_data in diff.to_create:
        try:
            VMRecord.objects.create(
                name=vm_data['name'],
                state=vm_data['state'],
                vcenter_id=vm_data.get('vcenter_id'),
                exist=True,
                last_synced=sync_time
            )
            result.created += 1
        except Exception as e:
            result.errors.append(f"Ошибка создания VM '{vm_data['name']}': {str(e)}")
    
    # Обновление существующих VM
    for vm_record, changes in diff.to_update:
        try:
            # Применяем изменения
            for field_name, change in changes.items():
                setattr(vm_record, field_name, change['new'])
            
            vm_record.last_synced = sync_time
            vm_record.save()
            # NetBox автоматически создаст ObjectChange запись
            
            result.updated += 1
        except Exception as e:
            result.errors.append(f"Ошибка обновления VM '{vm_record.name}': {str(e)}")
    
    # Подсчет неизмененных
    result.unchanged = len(diff.to_skip)
    
    # Пометка отсутствующих VM
    missing_ids = [vm.id for vm in diff.to_mark_missing]
    if missing_ids:
        try:
            VMRecord.objects.filter(id__in=missing_ids).update(
                exist=False,
                last_synced=sync_time
            )
            result.marked_missing = len(missing_ids)
        except Exception as e:
            result.errors.append(f"Ошибка пометки отсутствующих VM: {str(e)}")
    
    result.total_processed = len(diff.to_create) + len(diff.to_update) + len(diff.to_skip)
    
    return result


def sync_vcenter_vms() -> SyncResult:
    """
    Основная функция синхронизации VM из vCenter с NetBox.
    
    Реализует 3-фазный подход:
    1. Preparation - получение данных
    2. Diff - вычисление различий  
    3. Apply - применение изменений
    
    Returns:
        SyncResult с результатами синхронизации
    
    Example:
        >>> result = sync_vcenter_vms()
        >>> print(f"Создано: {result.created}, Обновлено: {result.updated}")
    """
    result = SyncResult()
    result.start()
    
    # ФАЗА 1: PREPARATION - Получение данных
    try:
        # Проверяем подключение к vCenter
        if not test_vcenter_connection():
            result.errors.append("Не удалось подключиться к vCenter")
            result.finish()
            return result

        # Проверяем/создаем ClusterType для vCenter
        cluster_type_name = cluster_info['cluster_type'].capitalize()  # 'vmware' -> 'VMware'
        cluster_type_slug = cluster_info['cluster_type'].lower()  # 'vmware'

        cluster_type, created = ClusterType.objects.get_or_create(
            slug=cluster_type_slug,
            defaults={'name': cluster_type_name}
        )

        # Проверяем/создаем Cluster для vCenter
        cluster_name = cluster_info['cluster_name']  # 'vcenet_obu'

        cluster, created = Cluster.objects.get_or_create(
            name=cluster_name,
            defaults={'type': cluster_type}
        )

        # Проверяем/создаем Custom Field для хранения ID из платформы виртуализации
        vm_cluster_id_field, created = CustomField.objects.get_or_create(
            name='vm_cluster_id',
            defaults={
                'label': 'VM Cluster ID',
                'type': 'text',
                'description': 'Уникальный идентификатор VM',
                'required': False,
            }
        )

        # Проверяем/создаем Custom Field для человекочитаемого названия ОС
        pretty_os_name_field, created = CustomField.objects.get_or_create(
            name='pretty_os_name',
            defaults={
                'label': 'OS',
                'type': 'text',
                'description': 'Операционная система',
                'required': False,
            }
        )

        # Привязываем Custom Fields к VirtualMachine если еще не привязано
        vm_content_type = ContentType.objects.get_for_model(VirtualMachine)
        if vm_content_type not in vm_cluster_id_field.object_types.all():
            vm_cluster_id_field.object_types.add(vm_content_type)
        if vm_content_type not in pretty_os_name_field.object_types.all():
            pretty_os_name_field.object_types.add(vm_content_type)

        # Получаем VM из vCenter
        vcenter_vms = get_vcenter_vms()
        
        # Получаем существующие VM из NetBox
        existing_vms = {vm.name: vm for vm in VMRecord.objects.all()}
        
    except Exception as e:
        result.errors.append(f"Ошибка получения данных: {str(e)}")
        result.finish()
        return result
    
    # ФАЗА 2: DIFF - Вычисление различий
    try:
        diff = calculate_diff(vcenter_vms, existing_vms)
    except Exception as e:
        result.errors.append(f"Ошибка вычисления различий: {str(e)}")
        result.finish()
        return result
    
    # ФАЗА 3: APPLY - Применение изменений
    try:
        result = apply_changes(diff, result)
    except Exception as e:
        result.errors.append(f"Ошибка применения изменений: {str(e)}")
    
    result.finish()
    return result


def get_sync_status() -> Dict:
    """
    Возвращает текущий статус синхронизации.
    
    Returns:
        Dict со статистикой:
            - total_vms: Общее количество VM в NetBox
            - existing_vms: Количество существующих VM
            - missing_vms: Количество отсутствующих VM
            - vcenter_available: Доступность vCenter
            - last_sync: Время последней синхронизации
    
    Example:
        >>> status = get_sync_status()
        >>> print(f"Всего VM: {status['total_vms']}")
    """
    total_vms = VMRecord.objects.count()
    existing_vms = VMRecord.objects.filter(exist=True).count()
    missing_vms = VMRecord.objects.filter(exist=False).count()
    
    # Получаем время последней синхронизации
    last_synced_vm = VMRecord.objects.filter(
        last_synced__isnull=False
    ).order_by('-last_synced').first()
    
    last_sync = last_synced_vm.last_synced if last_synced_vm else None
    
    return {
        'total_vms': total_vms,
        'existing_vms': existing_vms,
        'missing_vms': missing_vms,
        'vcenter_available': test_vcenter_connection(),
        'last_sync': last_sync
    }
