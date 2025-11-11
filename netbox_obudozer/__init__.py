"""
Плагин netbox_obudozer для NetBox

Плагин управления ресурсами ЦОД с интеграцией VMware vCenter.
"""
from netbox.plugins import PluginConfig


class ObudozerPluginConfig(PluginConfig):
    """
    Конфигурация плагина netbox_obudozer.

    Определяет базовые настройки плагина и его интеграцию с NetBox.
    """
    name = 'netbox_obudozer'
    verbose_name = 'NetBox Obudozer Plugin'
    description = 'Плагин управления ресурсами ЦОД с интеграцией VMware vCenter'
    version = '0.1.1'
    author = 'Stegantsev Victor'
    author_email = 'your.email@example.com'
    base_url = 'obudozer'
    required_settings = []
    default_settings = {
        # Настройки подключения к vCenter (будут использоваться при реальной интеграции)
        'vcenter_host': '',
        'vcenter_user': '',
        'vcenter_password': '',
        'vcenter_verify_ssl': False,

        # Настройки синхронизации
        'sync_enabled': True,
        'auto_sync_interval': 3600,  # секунды (1 час)
    }
    min_version = '4.4.0'


config = ObudozerPluginConfig
