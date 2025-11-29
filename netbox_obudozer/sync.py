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
from virtualization.models import ClusterType, Cluster, ClusterGroup, VirtualMachine, VirtualDisk
from extras.models import CustomField
from tqdm import tqdm

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
    cluster_group_name: str
) -> VMDiff:
    """
    ФАЗА 2: Вычисляет различия между vCenter и NetBox.

    Args:
        vcenter_vms: Список VM из vCenter
        existing_vms: Словарь существующих VM в NetBox (name -> VMRecord)
        cluster_group_name: Имя ClusterGroup (для default кластера)

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
            changes = get_field_changes(vm_record, vm_data, cluster_group_name)

            if changes:
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


def sync_vm_disks(vm: VirtualMachine, vcenter_disks: List[Dict]):
    """
    Синхронизирует диски виртуальной машины с данными из vCenter.

    Создает, обновляет или удаляет объекты VirtualDisk в NetBox согласно данным из vCenter.

    Args:
        vm: Объект VirtualMachine в NetBox
        vcenter_disks: Список дисков из vCenter (из vm_data['disks'])

    Example:
        >>> sync_vm_disks(vm, [{'name': 'Hard disk 1', 'size_mb': 51200, 'type': 'FlatVer2', 'thin_provisioned': True}])
    """
    if not vcenter_disks:
        # Если у ВМ нет дисков в vCenter, удаляем все существующие диски в NetBox
        VirtualDisk.objects.filter(virtual_machine=vm).delete()
        return

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
        else:
            # Создаем новый диск
            VirtualDisk.objects.create(
                virtual_machine=vm,
                name=disk_name,
                size=disk_data['size_mb'],
                description=description
            )

    # Удаляем диски, которых больше нет в vCenter
    for disk_name, disk in existing_disks.items():
        if disk_name not in vcenter_disk_names:
            disk.delete()


@transaction.atomic
def apply_changes(
    diff: VMDiff,
    result: SyncResult,
    cluster_type: ClusterType,
    cluster_group: ClusterGroup,
    cluster_group_name: str,
    vcenter_vms: List[Dict]
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

    Returns:
        Обновленный SyncResult
    """
    sync_time = timezone.now()

    # Создание новых VM
    if diff.to_create:
        for vm_data in tqdm(diff.to_create, desc="Creating VMs", unit="VM"):
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
                vm.save()

                result.created += 1
            except Exception as e:
                result.errors.append(f"Ошибка создания VM '{vm_data['name']}': {str(e)}")

    # Обновление существующих VM
    if diff.to_update:
        for vm, changes in tqdm(diff.to_update, desc="Updating VMs", unit="VM"):
            try:
                # Применяем изменения
                for field_name, change in changes.items():
                    if field_name == 'vcenter_id':
                        vm.custom_field_data = vm.custom_field_data or {}
                        vm.custom_field_data['vcenter_id'] = change['new']
                    elif field_name == 'vcenter_cluster':
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
                    else:
                        setattr(vm, field_name, change['new'])

                vm.custom_field_data = vm.custom_field_data or {}
                vm.custom_field_data['last_synced'] = sync_time.isoformat()
                vm.save()
                # NetBox автоматически создаст ObjectChange запись

                result.updated += 1
            except Exception as e:
                result.errors.append(f"Ошибка обновления VM '{vm.name}': {str(e)}")

    # Подсчет неизмененных
    result.unchanged = len(diff.to_skip)

    # Пометка отсутствующих VM статусом failed
    missing_ids = [vm.id for vm in diff.to_mark_missing]
    if missing_ids:
        try:
            # Массовое обновление статуса
            VirtualMachine.objects.filter(id__in=missing_ids).update(
                status='failed'
            )
            # Обновляем last_synced в Custom Fields с прогресс-баром
            missing_vms = VirtualMachine.objects.filter(id__in=missing_ids)
            for vm in tqdm(missing_vms, desc="Marking missing VMs", unit="VM"):
                vm.custom_field_data = vm.custom_field_data or {}
                vm.custom_field_data['last_synced'] = sync_time.isoformat()
                vm.save()

            result.marked_missing = len(missing_ids)
        except Exception as e:
            result.errors.append(f"Ошибка пометки отсутствующих VM: {str(e)}")

    # Синхронизация дисков для всех VM из vCenter
    # Создаем словарь для быстрого поиска VM данных по имени
    vcenter_vms_dict = {vm_data['name']: vm_data for vm_data in vcenter_vms}

    # Получаем все VM из ClusterGroup для синхронизации дисков
    all_cluster_group_vms = VirtualMachine.objects.filter(cluster__group=cluster_group)

    for vm in tqdm(all_cluster_group_vms, desc="Syncing VM disks", unit="VM"):
        try:
            # Находим данные ВМ из vCenter
            vm_data = vcenter_vms_dict.get(vm.name)
            if vm_data:
                # Синхронизируем диски
                sync_vm_disks(vm, vm_data.get('disks', []))
        except Exception as e:
            result.errors.append(f"Ошибка синхронизации дисков для VM '{vm.name}': {str(e)}")

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

        # Получаем/создаем ClusterType для vCenter
        cluster_type_value = get_cluster_type()
        cluster_type_slug = cluster_type_value.lower()
        cluster_type_name = cluster_type_value

        cluster_type, created = ClusterType.objects.get_or_create(
            slug=cluster_type_slug,
            defaults={'name': cluster_type_name}
        )

        # Получаем/создаем ClusterGroup из vcenter_name
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

        # Проверяем/создаем Custom Field для vCenter ID
        vcenter_id_field, created = CustomField.objects.get_or_create(
            name='vcenter_id',
            defaults={
                'label': 'vCenter ID',
                'type': 'text',
                'description': 'Уникальный идентификатор VM в vCenter',
                'required': False,
            }
        )

        # Проверяем/создаем Custom Field для времени синхронизации
        last_synced_field, created = CustomField.objects.get_or_create(
            name='last_synced',
            defaults={
                'label': 'Last Synced',
                'type': 'datetime',
                'description': 'Время последней синхронизации с vCenter',
                'required': False,
            }
        )

        # Проверяем/создаем Custom Field для имени кластера vCenter
        vcenter_cluster_field, created = CustomField.objects.get_or_create(
            name='vcenter_cluster',
            defaults={
                'label': 'vCenter Cluster',
                'type': 'text',
                'description': 'Имя кластера vCenter, в котором находится ВМ',
                'required': False,
            }
        )

        # Привязываем Custom Fields к VirtualMachine
        vm_content_type = ContentType.objects.get_for_model(VirtualMachine)
        for field in [vcenter_id_field, last_synced_field, vcenter_cluster_field]:
            if vm_content_type not in field.object_types.all():
                field.object_types.add(vm_content_type)

        # Получаем VM из vCenter
        vcenter_vms = get_vcenter_vms()

        # Получаем ВСЕ существующие VM (из любых кластеров)
        # Включая старый vcenter_obu - они автоматически переместятся при обновлении
        existing_vms = {
            vm.name: vm
            for vm in VirtualMachine.objects.all()
        }
        
    except Exception as e:
        result.errors.append(f"Ошибка получения данных: {str(e)}")
        result.finish()
        return result
    
    # ФАЗА 2: DIFF - Вычисление различий
    try:
        diff = calculate_diff(vcenter_vms, existing_vms, cluster_group_name)
    except Exception as e:
        result.errors.append(f"Ошибка вычисления различий: {str(e)}")
        result.finish()
        return result

    # ФАЗА 3: APPLY - Применение изменений
    try:
        result = apply_changes(
            diff,
            result,
            cluster_type,
            cluster_group,
            cluster_group_name,
            vcenter_vms
        )
    except Exception as e:
        result.errors.append(f"Ошибка применения изменений: {str(e)}")
    
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
