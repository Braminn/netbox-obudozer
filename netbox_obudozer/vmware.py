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


def get_cluster_group_name():
    """
    Получает имя ClusterGroup из конфигурации.

    Returns:
        str: vcenter_name из PLUGINS_CONFIG

    Raises:
        ValueError: Если vcenter_name не настроен
    """
    config = get_plugin_config()
    name = config.get('vcenter_name')
    if not name:
        raise ValueError("vcenter_name not configured in PLUGINS_CONFIG")
    return name


def get_cluster_type():
    """
    Получает тип кластера из конфигурации.

    Returns:
        str: cluster_type из PLUGINS_CONFIG (по умолчанию 'vmware')

    Example:
        >>> cluster_type = get_cluster_type()
        >>> print(cluster_type)
        vmware
    """
    config = get_plugin_config()
    return config.get('cluster_type', 'change_cluster_type')


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


def _extract_extraconfig_value(extra_config, key):
    """
    Извлекает значение из config.extraConfig по ключу.

    Args:
        extra_config: Список объектов config.extraConfig
        key: Ключ для поиска (например, 'guestinfo.vmtools.description')

    Returns:
        str или None: Значение найденного ключа или None

    Example:
        >>> description = _extract_extraconfig_value(vm.config.extraConfig, 'guestinfo.vmtools.description')
        >>> print(description)
        open-vm-tools 11.3.0 build 18090558
    """
    if not extra_config:
        return None

    try:
        # Используем генератор для поиска значения по ключу
        return next(
            (opt.value for opt in extra_config if getattr(opt, 'key', None) == key),
            None
        )
    except Exception as e:
        logger.warning(f"Failed to extract extraConfig value for key '{key}': {e}")
        return None


def _extract_guestinfo_detailed_data(extra_config):
    """
    Извлекает и парсит данные guestInfo.detailed.data для виртуальной машины.

    Args:
        extra_config: Список объектов config.extraConfig

    Returns:
        Dict: Словарь с информацией об ОС гостевой системы:
            - prettyName (str): Красивое имя ОС (например: "Ubuntu 22.04.3 LTS")
            - familyName (str): Семейство ОС (например: "Linux")
            - distroName (str): Имя дистрибутива (например: "ubuntu")
            - distroVersion (str): Версия дистрибутива (например: "22.04")
            - kernelVersion (str): Версия ядра (например: "5.15.0-91-generic")
            - bitness (str): Разрядность (например: "64")

    Example:
        >>> os_info = _extract_guestinfo_detailed_data(vm.config.extraConfig)
        >>> print(os_info['prettyName'])
        Ubuntu 22.04.3 LTS
    """
    import re

    # Дефолтные значения
    default_result = {
        "prettyName": None,
        "familyName": None,
        "distroName": None,
        "distroVersion": None,
        "kernelVersion": None,
        "bitness": None,
    }

    if not extra_config:
        return default_result

    try:
        # Извлекаем данные по ключу 'guestInfo.detailed.data'
        detailed_data = next(
            (opt.value for opt in extra_config if getattr(opt, 'key', None) == 'guestInfo.detailed.data'),
            None
        )

        # Если данные найдены, парсим их
        if detailed_data:
            parsed_data = dict(re.findall(r"(\w+)='([^']*)'", detailed_data))
            return {
                "prettyName": parsed_data.get('prettyName'),
                "familyName": parsed_data.get('familyName'),
                "distroName": parsed_data.get('distroName'),
                "distroVersion": parsed_data.get('distroVersion'),
                "kernelVersion": parsed_data.get('kernelVersion'),
                "bitness": parsed_data.get('bitness'),
            }
    except Exception as e:
        logger.warning(f"Failed to extract guestInfo.detailed.data: {e}")

    return default_result


def _extract_disk_info(devices):
    """
    Извлекает информацию о виртуальных дисках из списка устройств ВМ.

    Использует capacityInBytes (рекомендовано VMware с vSphere API 5.5+).
    Конвертирует из бинарных единиц (base-2) в десятичные (base-10) для соответствия vCenter UI.

    Формула: capacityInBytes / 1024^3 * 1000
    - VMware API возвращает в бинарных единицах (1 GiB = 1024 MiB)
    - vCenter UI отображает в десятичных единицах (1 GB = 1000 MB)
    - Пример: 40 GB в vCenter = 42949672960 bytes → 40000 MB

    Args:
        devices: Список устройств vim.vm.device (из config.hardware.device)

    Returns:
        List[Dict]: Список словарей с данными о дисках:
            - name (str): Метка диска (например, "Hard disk 1")
            - size_mb (int): Размер диска в мегабайтах (десятичные, как в vCenter UI)
            - type (str): Тип бэкенда диска (например, "FlatVer2")
            - thin_provisioned (bool): Thin provisioning (True) или thick (False)
            - file_name (str): Путь к файлу диска на datastore (например, "[datastore1] vm/vm.vmdk")

    Example:
        >>> disks = _extract_disk_info(vm.config.hardware.device)
        >>> for disk in disks:
        ...     print(f"{disk['name']}: {disk['size_mb']} MB, File: {disk['file_name']}")
        Hard disk 1: 40000 MB, File: [datastore1] vm01/vm01.vmdk
        Hard disk 2: 100000 MB, File: [datastore1] vm01/vm01_1.vmdk
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
                    # VMware API возвращает в бинарных единицах (base-2), но vCenter UI показывает в десятичных (base-10)
                    # Конвертируем: Bytes → GB (бинарные) → MB (десятичные) для соответствия vCenter UI
                    # Формула: capacityInBytes / 1024^3 * 1000 (аналогично netbox-sync)
                    if hasattr(device, 'capacityInBytes') and device.capacityInBytes:
                        size_mb = int(device.capacityInBytes / 1024 / 1024 / 1024 * 1000)
                    else:
                        size_mb = 0

                    disk_info = {
                        'name': device.deviceInfo.label if hasattr(device.deviceInfo, 'label') else 'Unknown',
                        'size_mb': size_mb,
                    }

                    # Получаем тип бэкенда, thin provisioning и путь к файлу
                    if hasattr(device, 'backing'):
                        backing_type = type(device.backing).__name__
                        # Извлекаем короткое имя типа (например, "FlatVer2BackingInfo" -> "FlatVer2")
                        if 'BackingInfo' in backing_type:
                            backing_type = backing_type.replace('vim.vm.device.VirtualDisk.', '').replace('BackingInfo', '')

                        disk_info['type'] = backing_type
                        disk_info['thin_provisioned'] = getattr(device.backing, 'thinProvisioned', False)
                        disk_info['file_name'] = getattr(device.backing, 'fileName', None)
                    else:
                        disk_info['type'] = 'Unknown'
                        disk_info['thin_provisioned'] = False
                        disk_info['file_name'] = None

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
            pathSet=['name', 'runtime.powerState', 'config.instanceUuid', 'config.uuid', 'runtime.host', 'config.hardware.device', 'config.hardware.numCPU', 'config.hardware.memoryMB', 'guest.ipAddress', 'guest.toolsStatus', 'config.extraConfig', 'config.createDate']
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
                    'vcpus': props.get('config.hardware.numCPU'),
                    'memory': props.get('config.hardware.memoryMB'),
                    'ip_address': props.get('guest.ipAddress'),
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

                # Получаем информацию о VMware Tools
                vm_data['tools_status'] = props.get('guest.toolsStatus')

                # Извлекаем данные из config.extraConfig
                extra_config = props.get('config.extraConfig')
                vm_data['vmtools_description'] = _extract_extraconfig_value(extra_config, 'guestinfo.vmtools.description')
                vm_data['vmtools_version_number'] = _extract_extraconfig_value(extra_config, 'guestinfo.vmtools.versionNumber')

                # Извлекаем детальную информацию об ОС из guestInfo.detailed.data
                os_info = _extract_guestinfo_detailed_data(extra_config)
                vm_data['os_pretty_name'] = os_info['prettyName']
                vm_data['os_family_name'] = os_info['familyName']
                vm_data['os_distro_name'] = os_info['distroName']
                vm_data['os_distro_version'] = os_info['distroVersion']
                vm_data['os_kernel_version'] = os_info['kernelVersion']
                vm_data['os_bitness'] = os_info['bitness']

                # Получаем дату создания VM (сохраняем как есть без преобразования)
                vm_data['creation_date'] = props.get('config.createDate')

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
