"""
Навигация плагина netbox_obudozer

Определяет пункты меню плагина в интерфейсе NetBox.
"""
from netbox.plugins import PluginMenuButton, PluginMenuItem
from netbox.choices import ButtonColorChoices


menu_items = (
    PluginMenuItem(
        link='plugins:netbox_obudozer:vmrecord_list',
        link_text='VM Records',
        buttons=(
            PluginMenuButton(
                link='plugins:netbox_obudozer:vmrecord_add',
                title='Add',
                icon_class='mdi mdi-plus-thick',
                color=ButtonColorChoices.GREEN
            ),
            PluginMenuButton(
                link='plugins:netbox_obudozer:sync_vcenter',
                title='Sync vCenter',
                icon_class='mdi mdi-sync',
                color=ButtonColorChoices.BLUE
            ),
        )
    ),
)
