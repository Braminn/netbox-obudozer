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
    version = '0.4.0'
    author = 'Stegantsev Victor'
    author_email = 'your.email@example.com'
    base_url = 'obudozer'
    api_urls = 'api.urls'  # Регистрация REST API URLs
    required_settings = []
    default_settings = {
        # Список vCenter-серверов. Для каждого элемента создаётся отдельная
        # ClusterGroup с именем name, к ней привязываются все кластеры и ВМ
        # этого vCenter. Формат элемента:
        #   {
        #       'host': 'vcenter.example.com',
        #       'name': 'Production vCenter',   # имя ClusterGroup в NetBox
        #       'user': 'username',
        #       'password': 'password',
        #       'verify_ssl': False,
        #       'cluster_type': 'vmware',       # необязательно, иначе общий cluster_type
        #   }
        'vcenters': [],

        # Настройки кластеров
        'cluster_type': '',  # Тип кластера в NetBox по умолчанию для всех vCenter

        # Настройки синхронизации
        'sync_enabled': True,
        'auto_sync_interval': 3600,  # секунды (1 час)

        # Настройки GitLab
        'gitlab_url': '',
        'gitlab_token': '',
        'gitlab_projects': [],       # список project ID или 'group/repo'
        'gitlab_verify_ssl': True,

        # Настройки отслеживания EOL версий ОС
        'eol_warning_days': 90,      # за сколько дней до eol_date статус становится "скоро истекает"
    }
    min_version = '4.4.0'
    template_extensions = 'template_extensions.template_extensions'

    def ready(self):
        """
        Вызывается при инициализации плагина.

        Импортирует jobs.py для регистрации фоновых задач.
        Импортирует signals.py для регистрации обработчиков сигналов.
        """
        super().ready()
        # Импортируем jobs для регистрации JobRunner
        from . import jobs  # noqa: F401
        # Импортируем signals для регистрации обработчиков синхронизации
        from . import signals  # noqa: F401


config = ObudozerPluginConfig
