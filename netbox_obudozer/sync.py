"""
Модуль синхронизации данных между vCenter и NetBox

Реализует 3-фазный подход синхронизации:
1. Preparation - получение и подготовка данных
2. Diff - вычисление различий
3. Apply - применение изменений

Использует встроенный NetBox механизм логирования изменений через ObjectChange.
"""
from typing import Dict, List, Tuple
from datetime import datetime
from django.db import transaction
from django.utils import timezone
from django.contrib.contenttypes.models import ContentType
from virtualization.models import ClusterType, Cluster, ClusterGroup, VirtualMachine, VirtualDisk
from extras.models import CustomField

from .vmware import get_vcenter_vms, test_vcenter_connection, get_cluster_group_name, get_cluster_type


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
        # Гарантируем что duration - это число и форматируем заранее
        duration_seconds = float(self.duration) if self.duration else 0.0
        duration_formatted = f"{duration_seconds:.2f}"
        return (
            f"Синхронизация завершена за {duration_formatted} сек:\n"
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
        self.to_update: List[Tuple[VirtualMachine, Dict]] = []
        self.to_skip: List[VirtualMachine] = []
        self.to_mark_missing: List[VirtualMachine] = []


def _normalize_datetime_for_comparison(value):
    """
    Нормализует datetime значение для корректного сравнения.

    Конвертирует как datetime объекты, так и ISO строки в datetime объекты,
    округленные до секунд. Это позволяет корректно сравнивать значения
    независимо от того, как они хранятся (datetime объект или строка).

    Args:
        value: datetime объект, ISO строка или None

    Returns:
        datetime объект округленный до секунд, или None

    Example:
        >>> dt1 = datetime(2024, 8, 20, 11, 19, 53, 244559)
        >>> dt2 = '2024-08-20 11:19:53.244559+00:00'
        >>> _normalize_datetime_for_comparison(dt1) == _normalize_datetime_for_comparison(dt2)
        True
    """
    if value is None:
        return None

    # Если это уже datetime объект
    if isinstance(value, datetime):
        return value.replace(microsecond=0)

    # Если это строка - парсим
    if isinstance(value, str):
        try:
            # Заменяем 'Z' на '+00:00' для правильного парсинга ISO формата
            dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
            return dt.replace(microsecond=0)
        except (ValueError, AttributeError):
            # Если не удалось парсить, возвращаем как есть
            return value

    return value


def get_field_changes(vm: VirtualMachine, vcenter_data: Dict, cluster_group_name: str) -> Dict:
    """
    Определяет какие поля изменились.

    Args:
        vm: Существующая VirtualMachine в NetBox
        vcenter_data: Новые данные из vCenter
        cluster_group_name: Имя ClusterGroup (для default кластера)

    Returns:
        Dict с измененными полями: {'field_name': {'old': old_value, 'new': new_value}}

    Example:
        >>> changes = get_field_changes(vm, {'state': 'running'}, 'vcenter.example.com')
        >>> print(changes)
        {'status': {'old': 'offline', 'new': 'active'}}
    """
    changes = {}

    # Конвертация state из vCenter в status NetBox
    vcenter_status = 'active' if vcenter_data['state'] == 'running' else 'offline'

    # Проверяем status
    if vm.status != vcenter_status:
        changes['status'] = {
            'old': vm.status,
            'new': vcenter_status
        }

    # Проверяем vcenter_id через Custom Fields
    current_vcenter_id = vm.custom_field_data.get('vcenter_id') if vm.custom_field_data else None
    new_vcenter_id = vcenter_data.get('vcenter_id')
    if new_vcenter_id and current_vcenter_id != new_vcenter_id:
        changes['vcenter_id'] = {
            'old': current_vcenter_id,
            'new': new_vcenter_id
        }

    # Проверяем vcenter_cluster через Custom Fields
    current_vcenter_cluster = vm.custom_field_data.get('vcenter_cluster') if vm.custom_field_data else None
    new_vcenter_cluster = vcenter_data.get('vcenter_cluster')

    # Определяем ожидаемое имя кластера
    expected_cluster_name = new_vcenter_cluster or cluster_group_name

    # Проверяем несоответствие кластера (для миграции из vcenter_obu)
    if vm.cluster.name != expected_cluster_name:
        changes['vcenter_cluster'] = {
            'old': current_vcenter_cluster,
            'new': new_vcenter_cluster
        }
    # Или изменение в custom field
    elif new_vcenter_cluster and current_vcenter_cluster != new_vcenter_cluster:
        changes['vcenter_cluster'] = {
            'old': current_vcenter_cluster,
            'new': new_vcenter_cluster
        }

    # Проверяем vcpus
    if vm.vcpus != vcenter_data.get('vcpus'):
        changes['vcpus'] = {
            'old': vm.vcpus,
            'new': vcenter_data.get('vcpus')
        }

    # Проверяем memory
    if vm.memory != vcenter_data.get('memory'):
        changes['memory'] = {
            'old': vm.memory,
            'new': vcenter_data.get('memory')
        }

    # Проверяем ip_address через Custom Fields
    current_ip = vm.custom_field_data.get('ip_address') if vm.custom_field_data else None
    new_ip = vcenter_data.get('ip_address')

    if current_ip != new_ip:
        changes['ip_address'] = {
            'old': current_ip,
            'new': new_ip
        }

    # Проверяем tools_status через Custom Fields
    current_tools_status = vm.custom_field_data.get('tools_status') if vm.custom_field_data else None
    new_tools_status = vcenter_data.get('tools_status')

    if current_tools_status != new_tools_status:
        changes['tools_status'] = {
            'old': current_tools_status,
            'new': new_tools_status
        }

    # Проверяем vmtools_description через Custom Fields
    current_vmtools_desc = vm.custom_field_data.get('vmtools_description') if vm.custom_field_data else None
    new_vmtools_desc = vcenter_data.get('vmtools_description')

    if current_vmtools_desc != new_vmtools_desc:
        changes['vmtools_description'] = {
            'old': current_vmtools_desc,
            'new': new_vmtools_desc
        }

    # Проверяем vmtools_version_number через Custom Fields
    current_vmtools_ver = vm.custom_field_data.get('vmtools_version_number') if vm.custom_field_data else None
    new_vmtools_ver = vcenter_data.get('vmtools_version_number')

    if current_vmtools_ver != new_vmtools_ver:
        changes['vmtools_version_number'] = {
            'old': current_vmtools_ver,
            'new': new_vmtools_ver
        }

    # Проверяем OS поля и creation_date через Custom Fields (используем цикл для уменьшения повторений)
    os_fields = [
        'os_pretty_name',
        'os_family_name',
        'os_distro_name',
        'os_distro_version',
        'os_kernel_version',
        'os_bitness',
        'creation_date',
    ]

    for field_name in os_fields:
        current_value = vm.custom_field_data.get(field_name) if vm.custom_field_data else None
        new_value = vcenter_data.get(field_name)

        # Специальная обработка для datetime полей
        if field_name == 'creation_date':
            current_value = _normalize_datetime_for_comparison(current_value)
            new_value = _normalize_datetime_for_comparison(new_value)

        if current_value != new_value:
            changes[field_name] = {
                'old': current_value,
                'new': new_value
            }

    # Если VM была помечена как failed, но теперь найдена в vCenter
    if vm.status == 'failed':
        changes['status'] = {
            'old': 'failed',
            'new': vcenter_status
        }

    return changes


def calculate_diff(
    vcenter_vms: List[Dict],
    existing_vms: Dict[str, VirtualMachine],
    cluster_group_name: str,
    logger=None
) -> VMDiff:
    """
    ФАЗА 2: Вычисляет различия между vCenter и NetBox.

    Args:
        vcenter_vms: Список VM из vCenter
        existing_vms: Словарь существующих VM в NetBox (name -> VMRecord)
        cluster_group_name: Имя ClusterGroup (для default кластера)
        logger: Опциональный logger для фоновых задач (JobRunner.logger)

    Returns:
        VMDiff объект с информацией о необходимых изменениях
    """
    diff = VMDiff()
    vcenter_names = set()
    logged_changes_count = 0
    max_log_changes = 10  # Логируем только первые 10 VM с изменениями

    # Проходим по всем VM из vCenter
    for vm_data in vcenter_vms:
        vm_name = vm_data['name']
        vcenter_names.add(vm_name)

        if vm_name in existing_vms:
            # VM существует - проверяем изменения
            vm_record = existing_vms[vm_name]
            changes = get_field_changes(vm_record, vm_data, cluster_group_name)

            if changes:
                # Логируем изменения для диагностики (только первые несколько)
                if logger and logged_changes_count < max_log_changes:
                    changes_str = ', '.join([f"{field}: '{change['old']}' → '{change['new']}'"
                                             for field, change in changes.items()])
                    logger.info(f"  [DIFF] VM '{vm_name}' будет обновлена: {changes_str}")
                    logged_changes_count += 1
                diff.to_update.append((vm_record, changes))
            else:
                diff.to_skip.append(vm_record)
        else:
            # VM не существует - нужно создать
            diff.to_create.append(vm_data)

    # Находим VM которых нет в vCenter
    for vm_name, vm_record in existing_vms.items():
        if vm_name not in vcenter_names and vm_record.status != 'failed':
            diff.to_mark_missing.append(vm_record)

    return diff


def get_or_create_cluster(
    cluster_name: str,
    cluster_type: ClusterType,
    cluster_group: ClusterGroup
) -> Cluster:
    """
    Получает или создает NetBox Cluster.

    Args:
        cluster_name: Имя кластера
        cluster_type: ClusterType объект
        cluster_group: ClusterGroup объект

    Returns:
        Cluster: Существующий или новый кластер
    """
    cluster, created = Cluster.objects.get_or_create(
        name=cluster_name,
        defaults={
            'type': cluster_type,
            'group': cluster_group,
            'status': 'active'
        }
    )

    # Обновить group если кластер существовал без него
    if not created and cluster.group != cluster_group:
        cluster.group = cluster_group
        cluster.save()

    return cluster


def sync_vm_disks(vm: VirtualMachine, vcenter_disks: List[Dict]) -> bool:
    """
    Синхронизирует диски виртуальной машины с данными из vCenter.

    Создает, обновляет или удаляет объекты VirtualDisk в NetBox согласно данным из vCenter.

    Args:
        vm: Объект VirtualMachine в NetBox
        vcenter_disks: Список дисков из vCenter (из vm_data['disks'])

    Returns:
        bool: True если были внесены изменения в диски, False если диски не изменились

    Example:
        >>> changed = sync_vm_disks(vm, [{'name': 'Hard disk 1', 'size_mb': 51200, 'type': 'FlatVer2', 'thin_provisioned': True}])
    """
    changes_made = False

    if not vcenter_disks:
        # Если у ВМ нет дисков в vCenter, удаляем все существующие диски в NetBox
        deleted_count = VirtualDisk.objects.filter(virtual_machine=vm).count()
        if deleted_count > 0:
            VirtualDisk.objects.filter(virtual_machine=vm).delete()
            changes_made = True
        return changes_made

    # Получаем существующие диски из NetBox
    existing_disks = {disk.name: disk for disk in VirtualDisk.objects.filter(virtual_machine=vm)}
    vcenter_disk_names = set()

    # Обрабатываем диски из vCenter
    for disk_data in vcenter_disks:
        disk_name = disk_data['name']
        vcenter_disk_names.add(disk_name)

        # Формируем описание диска с информацией о provisioning и файле
        description_parts = []
        if 'thin_provisioned' in disk_data:
            provision_type = "Thin" if disk_data['thin_provisioned'] else "Thick"
            description_parts.append(f"Provisioning: {provision_type}")
        if disk_data.get('file_name'):
            description_parts.append(f"File: {disk_data['file_name']}")

        description = ', '.join(description_parts) if description_parts else ''

        if disk_name in existing_disks:
            # Диск существует - проверяем и обновляем при необходимости
            disk = existing_disks[disk_name]
            updated = False

            if disk.size != disk_data['size_mb']:
                disk.size = disk_data['size_mb']
                updated = True

            if disk.description != description:
                disk.description = description
                updated = True

            if updated:
                disk.save()
                changes_made = True
        else:
            # Создаем новый диск
            VirtualDisk.objects.create(
                virtual_machine=vm,
                name=disk_name,
                size=disk_data['size_mb'],
                description=description
            )
            changes_made = True

    # Удаляем диски, которых больше нет в vCenter
    for disk_name, disk in existing_disks.items():
        if disk_name not in vcenter_disk_names:
            disk.delete()
            changes_made = True

    return changes_made


@transaction.atomic
def apply_changes(
    diff: VMDiff,
    result: SyncResult,
    cluster_type: ClusterType,
    cluster_group: ClusterGroup,
    cluster_group_name: str,
    vcenter_vms: List[Dict],
    logger=None
) -> SyncResult:
    """
    ФАЗА 3: Применяет изменения к базе данных.

    Выполняется в транзакции для обеспечения целостности данных.

    Args:
        diff: Объект с вычисленными различиями
        result: Объект для сохранения результатов
        cluster_type: Тип кластера (vmware)
        cluster_group: ClusterGroup объект
        cluster_group_name: Имя ClusterGroup (для default кластера)
        vcenter_vms: Список VM из vCenter с полными данными
        logger: Опциональный logger для фоновых задач (JobRunner.logger)

    Returns:
        Обновленный SyncResult
    """
    sync_time = timezone.now()

    # Создание новых VM
    if diff.to_create:
        if logger:
            logger.info(f"  → Создание {len(diff.to_create)} новых VM...")

        for idx, vm_data in enumerate(diff.to_create, 1):
            try:
                # Конвертация state → status
                status = 'active' if vm_data['state'] == 'running' else 'offline'

                # Определить имя кластера (или использовать ClusterGroup если не указан)
                vcenter_cluster_name = vm_data.get('vcenter_cluster') or cluster_group_name

                # Получить или создать кластер "на лету"
                vm_cluster = get_or_create_cluster(
                    vcenter_cluster_name,
                    cluster_type,
                    cluster_group
                )

                vm = VirtualMachine.objects.create(
                    name=vm_data['name'],
                    cluster=vm_cluster,  # Динамический кластер
                    status=status,
                    vcpus=vm_data.get('vcpus'),
                    memory=vm_data.get('memory'),
                )

                # Заполнение Custom Fields
                vm.custom_field_data = vm.custom_field_data or {}
                vm.custom_field_data['vcenter_id'] = vm_data.get('vcenter_id')
                vm.custom_field_data['last_synced'] = sync_time.isoformat()
                vm.custom_field_data['vcenter_cluster'] = vm_data.get('vcenter_cluster')
                vm.custom_field_data['ip_address'] = vm_data.get('ip_address')
                vm.custom_field_data['tools_status'] = vm_data.get('tools_status')
                vm.custom_field_data['vmtools_description'] = vm_data.get('vmtools_description')
                vm.custom_field_data['vmtools_version_number'] = vm_data.get('vmtools_version_number')
                vm.custom_field_data['os_pretty_name'] = vm_data.get('os_pretty_name')
                vm.custom_field_data['os_family_name'] = vm_data.get('os_family_name')
                vm.custom_field_data['os_distro_name'] = vm_data.get('os_distro_name')
                vm.custom_field_data['os_distro_version'] = vm_data.get('os_distro_version')
                vm.custom_field_data['os_kernel_version'] = vm_data.get('os_kernel_version')
                vm.custom_field_data['os_bitness'] = vm_data.get('os_bitness')
                vm.custom_field_data['creation_date'] = vm_data.get('creation_date')
                vm.save()

                # Синхронизируем диски для только что созданной VM
                sync_vm_disks(vm, vm_data.get('disks', []))

                result.created += 1

                # Логируем каждую 10-ую VM или последнюю
                if logger and (idx % 10 == 0 or idx == len(diff.to_create)):
                    logger.info(f"    ✓ Создано {idx}/{len(diff.to_create)} VM")

            except Exception as e:
                result.errors.append(f"Ошибка создания VM '{vm_data['name']}': {str(e)}")
                if logger:
                    logger.error(f"    ✗ Ошибка создания '{vm_data['name']}'")

        if logger:
            logger.info(f"  ✓ Создано VM: {result.created}")

    # Обновление существующих VM
    if diff.to_update:
        if logger:
            logger.info(f"  → Обновление {len(diff.to_update)} существующих VM...")

        for idx, (vm, changes) in enumerate(diff.to_update, 1):
            try:
                # Логируем причину обновления
                if logger:
                    changes_summary = ', '.join([f"{field}: {change['old']} → {change['new']}"
                                                  for field, change in changes.items()])
                    logger.info(f"    VM '{vm.name}': {changes_summary}")

                # Список custom fields для обработки в цикле
                custom_fields = [
                    'vcenter_id', 'ip_address', 'tools_status',
                    'vmtools_description', 'vmtools_version_number',
                    'os_pretty_name', 'os_family_name', 'os_distro_name',
                    'os_distro_version', 'os_kernel_version', 'os_bitness',
                    'creation_date'
                ]

                # Применяем изменения
                for field_name, change in changes.items():
                    if field_name == 'vcenter_cluster':
                        vm.custom_field_data = vm.custom_field_data or {}
                        vm.custom_field_data['vcenter_cluster'] = change['new']

                        # Также обновить NetBox cluster
                        new_vcenter_cluster = change['new'] or cluster_group_name
                        new_cluster = get_or_create_cluster(
                            new_vcenter_cluster,
                            cluster_type,
                            cluster_group
                        )
                        vm.cluster = new_cluster
                    elif field_name in custom_fields:
                        # Обработка всех custom fields в цикле
                        vm.custom_field_data = vm.custom_field_data or {}
                        vm.custom_field_data[field_name] = change['new']
                    else:
                        # Встроенные поля VirtualMachine (vcpus, memory, status)
                        setattr(vm, field_name, change['new'])

                vm.custom_field_data = vm.custom_field_data or {}
                vm.custom_field_data['last_synced'] = sync_time.isoformat()
                vm.save()
                # NetBox автоматически создаст ObjectChange запись

                # Синхронизируем диски для обновленной VM
                # Находим данные VM из vCenter для получения информации о дисках
                vm_data = next((v for v in vcenter_vms if v['name'] == vm.name), None)
                if vm_data:
                    sync_vm_disks(vm, vm_data.get('disks', []))

                result.updated += 1

                # Логируем каждую 10-ую VM или последнюю
                if logger and (idx % 10 == 0 or idx == len(diff.to_update)):
                    logger.info(f"    ✓ Обновлено {idx}/{len(diff.to_update)} VM")

            except Exception as e:
                result.errors.append(f"Ошибка обновления VM '{vm.name}': {str(e)}")
                if logger:
                    logger.error(f"    ✗ Ошибка обновления '{vm.name}'")

        if logger:
            logger.info(f"  ✓ Обновлено VM: {result.updated}")

    # Синхронизация дисков для VM без изменений
    # Это не создаст записи об изменении, если диски не изменились
    if diff.to_skip:
        if logger:
            logger.info(f"  → Синхронизация дисков для {len(diff.to_skip)} VM без изменений...")

        for idx, vm in enumerate(diff.to_skip, 1):
            try:
                # Находим данные VM из vCenter для получения информации о дисках
                vm_data = next((v for v in vcenter_vms if v['name'] == vm.name), None)
                if vm_data:
                    # Синхронизируем диски (изменения будут только если диски реально изменились)
                    sync_vm_disks(vm, vm_data.get('disks', []))

                # Логируем каждую 100-ую VM или последнюю (для неизмененных реже логируем)
                if logger and (idx % 100 == 0 or idx == len(diff.to_skip)):
                    logger.info(f"    ✓ Проверено дисков: {idx}/{len(diff.to_skip)} VM")

            except Exception as e:
                result.errors.append(f"Ошибка синхронизации дисков для VM '{vm.name}': {str(e)}")
                if logger:
                    logger.error(f"    ✗ Ошибка синхронизации дисков '{vm.name}'")

    # Подсчет неизмененных
    result.unchanged = len(diff.to_skip)
    if logger and result.unchanged > 0:
        logger.info(f"  ✓ Без изменений: {result.unchanged} VM")

    # Пометка отсутствующих VM статусом failed
    missing_ids = [vm.id for vm in diff.to_mark_missing]
    if missing_ids:
        if logger:
            logger.info(f"  → Пометка {len(missing_ids)} VM как недоступных...")

        try:
            # Массовое обновление статуса
            VirtualMachine.objects.filter(id__in=missing_ids).update(
                status='failed'
            )
            # Обновляем last_synced в Custom Fields
            missing_vms = VirtualMachine.objects.filter(id__in=missing_ids)
            for idx, vm in enumerate(missing_vms, 1):
                vm.custom_field_data = vm.custom_field_data or {}
                vm.custom_field_data['last_synced'] = sync_time.isoformat()
                vm.save()

                # Логируем каждую 10-ую VM или последнюю
                if logger and (idx % 10 == 0 or idx == len(missing_ids)):
                    logger.info(f"    ✓ Помечено {idx}/{len(missing_ids)} VM")

            result.marked_missing = len(missing_ids)

            if logger:
                logger.info(f"  ✓ Помечено недоступными: {result.marked_missing}")

        except Exception as e:
            result.errors.append(f"Ошибка пометки отсутствующих VM: {str(e)}")
            if logger:
                logger.error(f"  ✗ Ошибка пометки отсутствующих VM")

    result.total_processed = len(diff.to_create) + len(diff.to_update) + len(diff.to_skip)

    return result


def sync_vcenter_vms(logger=None) -> SyncResult:
    """
    Основная функция синхронизации VM из vCenter с NetBox.

    Реализует 3-фазный подход:
    1. Preparation - получение данных
    2. Diff - вычисление различий
    3. Apply - применение изменений

    Args:
        logger: Опциональный logger для фоновых задач (JobRunner.logger)

    Returns:
        SyncResult с результатами синхронизации

    Example:
        >>> result = sync_vcenter_vms()
        >>> print(f"Создано: {result.created}, Обновлено: {result.updated}")
    """
    result = SyncResult()
    result.start()

    # ФАЗА 1: PREPARATION - Получение данных
    if logger:
        logger.info("📋 ФАЗА 1: Подготовка данных")

    try:
        if logger:
            logger.info("  → Проверка подключения к vCenter...")
        # Проверяем подключение к vCenter
        if not test_vcenter_connection():
            result.errors.append("Не удалось подключиться к vCenter")
            if logger:
                logger.error("  ❌ vCenter недоступен")
            result.finish()
            return result

        if logger:
            logger.info("  ✓ vCenter доступен")

        # Получаем/создаем ClusterType для vCenter
        if logger:
            logger.info("  → Проверка ClusterType...")

        cluster_type_value = get_cluster_type()
        cluster_type_slug = cluster_type_value.lower()
        cluster_type_name = cluster_type_value

        cluster_type, created = ClusterType.objects.get_or_create(
            slug=cluster_type_slug,
            defaults={'name': cluster_type_name}
        )

        if logger:
            logger.info(f"  ✓ ClusterType: {cluster_type.name}")

        # Получаем/создаем ClusterGroup из vcenter_name
        if logger:
            logger.info("  → Проверка ClusterGroup...")

        cluster_group_name = get_cluster_group_name()

        # Получаем vcenter_host для описания
        from .vmware import get_plugin_config
        config = get_plugin_config()
        vcenter_host = config.get('vcenter_host', cluster_group_name)

        cluster_group, created = ClusterGroup.objects.get_or_create(
            name=cluster_group_name,
            defaults={
                'slug': cluster_group_name.replace('.', '-').replace('_', '-'),
                'description': f'vCenter clusters from {vcenter_host}'
            }
        )

        if logger:
            logger.info(f"  ✓ ClusterGroup: {cluster_group.name}")

        # Проверяем/создаем Custom Fields
        if logger:
            logger.info("  → Проверка Custom Fields...")

        vcenter_id_field, created = CustomField.objects.get_or_create(
            name='vcenter_id',
            defaults={
                'label': 'vCenter ID',
                'type': 'text',
                'description': 'Уникальный идентификатор VM в vCenter',
                'required': False,
            }
        )

        last_synced_field, created = CustomField.objects.get_or_create(
            name='last_synced',
            defaults={
                'label': 'Last Synced',
                'type': 'datetime',
                'description': 'Время последней синхронизации с vCenter',
                'required': False,
            }
        )

        vcenter_cluster_field, created = CustomField.objects.get_or_create(
            name='vcenter_cluster',
            defaults={
                'label': 'vCenter Cluster',
                'type': 'text',
                'description': 'Имя кластера vCenter, в котором находится ВМ',
                'required': False,
            }
        )

        ip_address_field, created = CustomField.objects.get_or_create(
            name='ip_address',
            defaults={
                'label': 'IP Address',
                'type': 'text',
                'description': 'Primary IP address from vCenter (guest.ipAddress)',
                'required': False,
            }
        )

        tools_status_field, created = CustomField.objects.get_or_create(
            name='tools_status',
            defaults={
                'label': 'VMware Tools Status',
                'type': 'text',
                'description': 'VMware Tools status from guest.toolsStatus',
                'required': False,
            }
        )

        vmtools_description_field, created = CustomField.objects.get_or_create(
            name='vmtools_description',
            defaults={
                'label': 'VMware Tools Description',
                'type': 'text',
                'description': 'VMware Tools description from guestinfo.vmtools.description',
                'required': False,
            }
        )

        vmtools_version_number_field, created = CustomField.objects.get_or_create(
            name='vmtools_version_number',
            defaults={
                'label': 'VMware Tools Version Number',
                'type': 'text',
                'description': 'VMware Tools version number from guestinfo.vmtools.versionNumber',
                'required': False,
            }
        )

        os_pretty_name_field, created = CustomField.objects.get_or_create(
            name='os_pretty_name',
            defaults={
                'label': 'OS Pretty Name',
                'type': 'text',
                'description': 'OS pretty name from guestInfo.detailed.data (e.g., "Ubuntu 22.04.3 LTS")',
                'required': False,
            }
        )

        os_family_name_field, created = CustomField.objects.get_or_create(
            name='os_family_name',
            defaults={
                'label': 'OS Family Name',
                'type': 'text',
                'description': 'OS family name from guestInfo.detailed.data (e.g., "Linux")',
                'required': False,
            }
        )

        os_distro_name_field, created = CustomField.objects.get_or_create(
            name='os_distro_name',
            defaults={
                'label': 'OS Distro Name',
                'type': 'text',
                'description': 'OS distribution name from guestInfo.detailed.data (e.g., "ubuntu")',
                'required': False,
            }
        )

        os_distro_version_field, created = CustomField.objects.get_or_create(
            name='os_distro_version',
            defaults={
                'label': 'OS Distro Version',
                'type': 'text',
                'description': 'OS distribution version from guestInfo.detailed.data (e.g., "22.04")',
                'required': False,
            }
        )

        os_kernel_version_field, created = CustomField.objects.get_or_create(
            name='os_kernel_version',
            defaults={
                'label': 'OS Kernel Version',
                'type': 'text',
                'description': 'OS kernel version from guestInfo.detailed.data (e.g., "5.15.0-91-generic")',
                'required': False,
            }
        )

        os_bitness_field, created = CustomField.objects.get_or_create(
            name='os_bitness',
            defaults={
                'label': 'OS Bitness',
                'type': 'text',
                'description': 'OS bitness from guestInfo.detailed.data (e.g., "64")',
                'required': False,
            }
        )

        creation_date_field, created = CustomField.objects.get_or_create(
            name='creation_date',
            defaults={
                'label': 'Creation Date',
                'type': 'datetime',
                'description': 'VM creation date from config.createDate',
                'required': False,
            }
        )

        # Custom field для отображения связанных OBU Services
        # Lazy import чтобы избежать циклических зависимостей
        from .models import ObuServices

        obu_services_field, created = CustomField.objects.get_or_create(
            name='obu_services',
            defaults={
                'label': 'OBU Services',
                'type': 'multiobject',
                'description': 'Услуги, к которым привязана виртуальная машина',
                'required': False,
                'ui_visible': 'always',
                'ui_editable': 'no',  # Read-only, управляется через ServiceVMAssignment
            }
        )

        # Устанавливаем related_object_type для multiobject поля
        # Это делается отдельно, так как это ForeignKey, а не простое поле
        if created or not obu_services_field.related_object_type:
            obu_services_field.related_object_type = ContentType.objects.get_for_model(ObuServices)
            obu_services_field.save()

        # Custom field-флаг: есть ли у VM хотя бы одна привязанная услуга
        has_obu_services_field, _ = CustomField.objects.get_or_create(
            name='has_obu_services',
            defaults={
                'label': 'Имеет OBU сервис',
                'type': 'boolean',
                'description': 'True если у виртуальной машины есть хотя бы одна привязанная услуга OBU',
                'required': False,
                'ui_visible': 'always',
                'ui_editable': 'no',
            }
        )

        # Привязываем Custom Fields к VirtualMachine
        vm_content_type = ContentType.objects.get_for_model(VirtualMachine)
        for field in [vcenter_id_field, last_synced_field, vcenter_cluster_field, ip_address_field,
                      tools_status_field, vmtools_description_field, vmtools_version_number_field,
                      os_pretty_name_field, os_family_name_field, os_distro_name_field,
                      os_distro_version_field, os_kernel_version_field, os_bitness_field,
                      creation_date_field, obu_services_field, has_obu_services_field]:
            if vm_content_type not in field.object_types.all():
                field.object_types.add(vm_content_type)

        if logger:
            logger.info("  ✓ Custom Fields готовы")

        # Получаем VM из vCenter
        if logger:
            logger.info("  → Получение VM из vCenter...")

        vcenter_vms = get_vcenter_vms()

        if logger:
            logger.info(f"  ✓ Получено {len(vcenter_vms)} VM из vCenter")

        # Получаем ВСЕ существующие VM (из любых кластеров)
        # Включая старый vcenter_obu - они автоматически переместятся при обновлении
        if logger:
            logger.info("  → Запрос существующих VM из NetBox...")

        existing_vms = {
            vm.name: vm
            for vm in VirtualMachine.objects.all()
        }

        if logger:
            logger.info(f"  ✓ Найдено {len(existing_vms)} VM в NetBox")
        
    except Exception as e:
        result.errors.append(f"Ошибка получения данных: {str(e)}")
        if logger:
            logger.error(f"  ❌ {str(e)}")
        result.finish()
        return result

    # ФАЗА 2: DIFF - Вычисление различий
    if logger:
        logger.info("")
        logger.info("🔍 ФАЗА 2: Анализ различий")

    try:
        diff = calculate_diff(vcenter_vms, existing_vms, cluster_group_name, logger=logger)

        if logger:
            logger.info(f"  → Создать: {len(diff.to_create)} VM")
            logger.info(f"  → Обновить: {len(diff.to_update)} VM")
            logger.info(f"  → Без изменений: {len(diff.to_skip)} VM")
            logger.info(f"  → Пометить недоступными: {len(diff.to_mark_missing)} VM")

    except Exception as e:
        result.errors.append(f"Ошибка вычисления различий: {str(e)}")
        if logger:
            logger.error(f"  ❌ {str(e)}")
        result.finish()
        return result

    # ФАЗА 3: APPLY - Применение изменений
    if logger:
        logger.info("")
        logger.info("💾 ФАЗА 3: Применение изменений")

    try:
        result = apply_changes(
            diff,
            result,
            cluster_type,
            cluster_group,
            cluster_group_name,
            vcenter_vms,
            logger=logger
        )
    except Exception as e:
        result.errors.append(f"Ошибка применения изменений: {str(e)}")
        if logger:
            logger.error(f"  ❌ {str(e)}")
    
    result.finish()
    return result


def get_sync_status(cluster_group_name: str = None) -> Dict:
    """
    Возвращает текущий статус синхронизации для ClusterGroup.

    Args:
        cluster_group_name: Имя ClusterGroup (по умолчанию из vcenter_host)

    Returns:
        Dict со статистикой:
            - total_vms: Общее количество VM в ClusterGroup
            - active_vms: Количество активных VM (running)
            - offline_vms: Количество остановленных VM (stopped)
            - failed_vms: Количество отсутствующих в vCenter VM
            - vcenter_available: Доступность vCenter
            - last_sync: Время последней синхронизации
            - cluster_count: Количество кластеров в группе

    Example:
        >>> status = get_sync_status()
        >>> print(f"Всего VM: {status['total_vms']}, Кластеров: {status['cluster_count']}")
    """
    try:
        if cluster_group_name is None:
            cluster_group_name = get_cluster_group_name()

        cluster_group = ClusterGroup.objects.get(name=cluster_group_name)
        vms = VirtualMachine.objects.filter(cluster__group=cluster_group)

        total_vms = vms.count()
        active_vms = vms.filter(status='active').count()
        offline_vms = vms.filter(status='offline').count()
        failed_vms = vms.filter(status='failed').count()
        cluster_count = Cluster.objects.filter(group=cluster_group).count()

        # Получаем время последней синхронизации из Custom Fields
        last_sync = None
        for vm in vms.order_by('-last_updated')[:1]:
            last_synced_str = vm.custom_field_data.get('last_synced') if vm.custom_field_data else None
            if last_synced_str:
                try:
                    from dateutil import parser
                    last_sync = parser.parse(last_synced_str)
                except:
                    pass
                break

        return {
            'total_vms': total_vms,
            'active_vms': active_vms,
            'offline_vms': offline_vms,
            'failed_vms': failed_vms,
            'vcenter_available': test_vcenter_connection(),
            'last_sync': last_sync,
            'cluster_count': cluster_count,
        }
    except ClusterGroup.DoesNotExist:
        return {
            'total_vms': 0,
            'active_vms': 0,
            'offline_vms': 0,
            'failed_vms': 0,
            'vcenter_available': test_vcenter_connection(),
            'last_sync': None,
            'cluster_count': 0,
        }


def sync_cluster_to_service(service_id: int, cluster_id: int, logger=None) -> Dict:
    """
    Синхронизирует все VM из указанного кластера в указанную услугу.

    Добавляет VM из кластера к услуге, не трогая существующие привязки к другим
    услугам. VM, которые уже привязаны к этой услуге, пропускаются.
    VM, которые были удалены из кластера (не существуют в NetBox), игнорируются.

    Args:
        service_id: PK услуги ObuServices
        cluster_id: PK кластера Cluster
        logger: Опциональный logger для фоновых задач

    Returns:
        Dict с ключами: added (int), skipped (int), errors (list)
    """
    from .models import ObuServices, ServiceVMAssignment

    result = {'added': 0, 'skipped': 0, 'errors': []}

    try:
        service = ObuServices.objects.get(pk=service_id)
    except ObuServices.DoesNotExist:
        msg = f"Услуга с id={service_id} не найдена"
        result['errors'].append(msg)
        if logger:
            logger.error(f"  ❌ {msg}")
        return result

    try:
        cluster = Cluster.objects.get(pk=cluster_id)
    except Cluster.DoesNotExist:
        msg = f"Кластер с id={cluster_id} не найден"
        result['errors'].append(msg)
        if logger:
            logger.error(f"  ❌ {msg}")
        return result

    if logger:
        logger.info(f"  → Синхронизация кластера «{cluster.name}» → услуга «{service.name}»")

    cluster_vms = VirtualMachine.objects.filter(cluster=cluster)
    existing_vm_ids = set(
        ServiceVMAssignment.objects.filter(service=service)
        .values_list('virtual_machine_id', flat=True)
    )

    to_add = [vm for vm in cluster_vms if vm.pk not in existing_vm_ids]

    with transaction.atomic():
        for vm in to_add:
            try:
                ServiceVMAssignment.objects.create(service=service, virtual_machine=vm)
                result['added'] += 1
            except Exception as e:
                result['errors'].append(f"VM {vm.name}: {e}")

        result['skipped'] = cluster_vms.count() - result['added']

    if logger:
        logger.info(f"  ✓ Добавлено: {result['added']}, пропущено (уже было): {result['skipped']}")
        if result['errors']:
            logger.warning(f"  ⚠️ Ошибок: {len(result['errors'])}")

    return result
