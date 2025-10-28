from netbox.plugins import PluginConfig


class ObudozerPluginConfig(PluginConfig):
    name = 'netbox_obudozer'
    verbose_name = 'NetBox Obudozer Plugin'
    description = 'Плагин управления ресурсами ЦОД.'
    version = '0.1.0'
    author = 'Stegantsev Victor'
    author_email = 'your.email@example.com'
    base_url = 'obudozer'
    required_settings = []
    default_settings = {}
    min_version = '3.5.0'


config = ObudozerPluginConfig
