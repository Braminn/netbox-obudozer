"""
Навигация плагина netbox_obudozer

Определяет пункты меню плагина в интерфейсе NetBox.
"""
from netbox.plugins import PluginMenuButton, PluginMenuItem
from netbox.choices import ButtonColorChoices


menu_items = (
    PluginMenuItem(
        link='plugins:netbox_obudozer:sync_vcenter',
        link_text='vCenter Sync',
        buttons=(
            PluginMenuButton(
                link='plugins:netbox_obudozer:sync_vcenter',
                title='Sync Now',
                icon_class='mdi mdi-sync',
                color=ButtonColorChoices.BLUE
            ),
        )
    ),
)
