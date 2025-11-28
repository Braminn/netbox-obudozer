"""
Модуль интеграции с VMware vCenter

Содержит функции для получения данных о виртуальных машинах из vCenter.
Использует библиотеку pyVmomi для подключения к vCenter API.
"""
from typing import List, Dict
import logging
import atexit

from pyVim.connect import SmartConnect, Disconnect
from pyVmomi import vim, vmodl
from tqdm import tqdm

# Настройка логирования
logger = logging.getLogger('netbox.plugins.netbox_obudozer')


def get_plugin_config():
    """
    Получает конфигурацию плагина из settings.

    Returns:
        dict: Словарь с настройками плагина
    """
    from django.conf import settings
    return settings.PLUGINS_CONFIG.get('netbox_obudozer', {})


# Имя кластера vCenter для синхронизации
cluster_info = {
    'cluster_name': 'vcenter_obu',
    'cluster_type': 'vmware',
}


def _connect_vcenter():
    """
    Устанавливает подключение к vCenter.

    Returns:
        ServiceInstance: Объект подключения к vCenter

    Raises:
        ValueError: Если не настроены учетные данные vCenter
        Exception: Если не удалось подключиться к vCenter
    """
    config = get_plugin_config()

    host = config.get('vcenter_host')
    user = config.get('vcenter_user')
    password = config.get('vcenter_password')
    verify_ssl = config.get('vcenter_verify_ssl', False)

    if not all([host, user, password]):
        raise ValueError("vCenter credentials not configured in PLUGINS_CONFIG")

    try:
        si = SmartConnect(
            host=host,
            user=user,
            pwd=password,
            disableSslCertValidation=not verify_ssl
        )

        # Регистрируем автоматическое отключение при завершении
        atexit.register(Disconnect, si)

        logger.info(f"Successfully connected to vCenter: {host}")
        return si

    except Exception as e:
        logger.error(f"Failed to connect to vCenter {host}: {e}")
        raise


def _map_power_state(power_state):
    """
    Конвертирует состояние ВМ из vCenter в формат плагина.

    Args:
        power_state: vim.VirtualMachinePowerState (строка)

    Returns:
        str: 'running' или 'stopped'
    """
    # vCenter возвращает: 'poweredOn', 'poweredOff', 'suspended'
    if power_state == 'poweredOn':
        return 'running'
    else:
        # poweredOff и suspended считаем остановленными
        return 'stopped'


def _extract_disk_info(devices):
    """
    Извлекает информацию о виртуальных дисках из списка устройств ВМ.

    Args:
        devices: Список устройств vim.vm.device (из config.hardware.device)

    Returns:
        List[Dict]: Список словарей с данными о дисках:
            - name (str): Метка диска (например, "Hard disk 1")
            - size_mb (int): Размер диска в мегабайтах
            - type (str): Тип бэкенда диска (например, "FlatVer2")
            - thin_provisioned (bool): Thin provisioning (True) или thick (False)

    Example:
        >>> disks = _extract_disk_info(vm.config.hardware.device)
        >>> for disk in disks:
        ...     print(f"{disk['name']}: {disk['size_mb']} MB")
        Hard disk 1: 51200 MB
        Hard disk 2: 102400 MB
    """
    disks = []

    if not devices:
        return disks

    try:
        for device in devices:
            # Проверяем, является ли устройство виртуальным диском
            if type(device).__name__ == 'vim.vm.device.VirtualDisk':
                try:
                    # Извлекаем информацию о диске
                    disk_info = {
                        'name': device.deviceInfo.label if hasattr(device.deviceInfo, 'label') else 'Unknown',
                        'size_mb': int(device.capacityInKB / 1024) if hasattr(device, 'capacityInKB') else 0,
                    }

                    # Получаем тип бэкенда и thin provisioning
                    if hasattr(device, 'backing'):
                        backing_type = type(device.backing).__name__
                        # Извлекаем короткое имя типа (например, "FlatVer2BackingInfo" -> "FlatVer2")
                        if 'BackingInfo' in backing_type:
                            backing_type = backing_type.replace('vim.vm.device.VirtualDisk.', '').replace('BackingInfo', '')

                        disk_info['type'] = backing_type
                        disk_info['thin_provisioned'] = getattr(device.backing, 'thinProvisioned', False)
                    else:
                        disk_info['type'] = 'Unknown'
                        disk_info['thin_provisioned'] = False

                    disks.append(disk_info)

                except Exception as e:
                    logger.warning(f"Failed to extract disk info for device {device}: {e}")
                    continue

    except Exception as e:
        logger.warning(f"Failed to iterate through devices: {e}")

    return disks


def get_vcenter_vms() -> List[Dict]:
    """
    Получает список виртуальных машин из VMware vCenter.

    Использует PropertyCollector API для эффективного получения всех данных
    одним запросом вместо множества отдельных запросов для каждой ВМ.

    Returns:
        List[Dict]: Список словарей с данными о VM, каждый содержит:
            - name (str): Имя виртуальной машины
            - state (str): Состояние VM ('running' или 'stopped')
            - vcenter_id (str): Уникальный идентификатор VM в vCenter (instanceUuid)

    Raises:
        ValueError: Если не настроены учетные данные vCenter
        Exception: При ошибке подключения или получения данных

    Example:
        >>> vms = get_vcenter_vms()
        >>> for vm in vms:
        ...     print(f"{vm['name']}: {vm['state']}")
        vm01: running
        vm02: stopped
        ...
    """
    vms = []
    si = None

    try:
        # Подключаемся к vCenter
        logger.info("Connecting to vCenter...")
        si = _connect_vcenter()
        content = si.RetrieveContent()

        # Создаем container view для всех VirtualMachine объектов
        container = content.rootFolder
        container_view = content.viewManager.CreateContainerView(
            container, [vim.VirtualMachine], True
        )

        # Определяем нужные свойства для получения
        property_spec = vmodl.query.PropertyCollector.PropertySpec(
            type=vim.VirtualMachine,
            pathSet=['name', 'runtime.powerState', 'config.instanceUuid', 'config.uuid', 'runtime.host', 'config.hardware.device']
        )

        # Определяем объекты для запроса
        traversal_spec = vmodl.query.PropertyCollector.TraversalSpec(
            type=vim.ContainerView,
            path='view',
            skip=False
        )

        object_spec = vmodl.query.PropertyCollector.ObjectSpec(
            obj=container_view,
            skip=True,
            selectSet=[traversal_spec]
        )

        # Создаем спецификацию фильтра
        filter_spec = vmodl.query.PropertyCollector.FilterSpec(
            propSet=[property_spec],
            objectSet=[object_spec]
        )

        # Получаем ВСЕ свойства ВСЕХ ВМ одним запросом!
        logger.info("Retrieving VM properties from vCenter (single request)...")
        options = vmodl.query.PropertyCollector.RetrieveOptions()
        result = content.propertyCollector.RetrievePropertiesEx(
            specSet=[filter_spec],
            options=options
        )

        # Собираем все объекты из всех страниц (если есть pagination)
        all_objects = []
        while result:
            all_objects.extend(result.objects)
            if result.token:
                result = content.propertyCollector.ContinueRetrievePropertiesEx(token=result.token)
            else:
                break

        # Обрабатываем результаты с прогресс-баром
        logger.info(f"Processing {len(all_objects)} VMs...")
        for obj in tqdm(all_objects, desc="Processing VMs", unit="VM"):
            try:
                # Собираем свойства в словарь
                props = {}
                for prop in obj.propSet:
                    props[prop.name] = prop.val

                # Формируем данные ВМ
                vm_data = {
                    'name': props.get('name', 'Unknown'),
                    'state': _map_power_state(props.get('runtime.powerState', 'poweredOff')),
                    'vcenter_id': props.get('config.instanceUuid') or props.get('config.uuid', ''),
                }

                # Получаем имя кластера vCenter
                try:
                    host = props.get('runtime.host')
                    if host and hasattr(host, 'parent') and hasattr(host.parent, 'name'):
                        vm_data['vcenter_cluster'] = host.parent.name
                    else:
                        vm_data['vcenter_cluster'] = None
                except Exception as e:
                    logger.warning(f"Failed to get cluster for VM {vm_data['name']}: {e}")
                    vm_data['vcenter_cluster'] = None

                # Получаем информацию о дисках
                devices = props.get('config.hardware.device')
                vm_data['disks'] = _extract_disk_info(devices)

                vms.append(vm_data)

            except Exception as e:
                vm_name = props.get('name', 'unknown') if 'props' in locals() else 'unknown'
                logger.warning(f"Failed to process VM {vm_name}: {e}")
                continue

        # Уничтожаем view
        container_view.Destroy()

        logger.info(f"Successfully retrieved {len(vms)} VMs from vCenter using PropertyCollector")

    except Exception as e:
        logger.error(f"Error retrieving VMs from vCenter: {e}")
        raise

    finally:
        # Отключаемся от vCenter
        if si:
            try:
                Disconnect(si)
            except:
                pass

    return vms


def test_vcenter_connection() -> bool:
    """
    Проверяет подключение к vCenter.

    Выполняет тестовое подключение к vCenter и проверяет доступность API.

    Returns:
        bool: True если подключение успешно, False в противном случае

    Example:
        >>> if test_vcenter_connection():
        ...     print("vCenter доступен")
        ... else:
        ...     print("Ошибка подключения к vCenter")
    """
    si = None
    try:
        # Подключаемся к vCenter
        si = _connect_vcenter()

        # Проверяем, что можем получить content
        content = si.RetrieveContent()

        # Проверяем доступность основных API
        _ = content.about.fullName

        logger.info("vCenter connection test successful")
        return True

    except Exception as e:
        logger.error(f"vCenter connection test failed: {e}")
        return False

    finally:
        # Отключаемся от vCenter
        if si:
            try:
                Disconnect(si)
            except:
                pass
