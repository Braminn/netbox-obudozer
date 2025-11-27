"""
Модуль интеграции с VMware vCenter

Содержит функции для получения данных о виртуальных машинах из vCenter.
Использует библиотеку pyVmomi для подключения к vCenter API.
"""
from typing import List, Dict
import logging
import atexit

from pyVim.connect import SmartConnect, Disconnect
from pyVmomi import vim
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
        property_spec = vim.PropertyFilterSpec.PropertySpec(
            type=vim.VirtualMachine,
            pathSet=['name', 'runtime.powerState', 'config.instanceUuid', 'config.uuid']
        )

        # Определяем объекты для запроса
        object_spec = vim.PropertyFilterSpec.ObjectSpec(
            obj=container_view,
            skip=True,
            selectSet=[vim.TraversalSpec(
                type=vim.ContainerView,
                path='view',
                skip=False
            )]
        )

        # Создаем спецификацию фильтра
        filter_spec = vim.PropertyFilterSpec(
            propSet=[property_spec],
            objectSet=[object_spec]
        )

        # Получаем ВСЕ свойства ВСЕХ ВМ одним запросом!
        logger.info("Retrieving VM properties from vCenter (single request)...")
        options = vim.RetrieveOptions()
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
