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

    Подключается к vCenter через pyVmomi и извлекает информацию о всех
    виртуальных машинах.

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
        si = _connect_vcenter()

        # Получаем content
        content = si.RetrieveContent()

        # Создаем container view для всех VirtualMachine объектов
        container = content.rootFolder
        view_type = [vim.VirtualMachine]
        recursive = True

        container_view = content.viewManager.CreateContainerView(
            container, view_type, recursive
        )

        # Обрабатываем все ВМ
        for vm in container_view.view:
            try:
                # Получаем данные ВМ
                vm_data = {
                    'name': vm.name,
                    'state': _map_power_state(vm.runtime.powerState) if vm.runtime else 'stopped',
                    'vcenter_id': vm.config.instanceUuid if vm.config else vm._moId,
                }
                vms.append(vm_data)

            except Exception as e:
                logger.warning(f"Failed to get data for VM {getattr(vm, 'name', 'unknown')}: {e}")
                continue

        # Уничтожаем view
        container_view.Destroy()

        logger.info(f"Successfully retrieved {len(vms)} VMs from vCenter")

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
