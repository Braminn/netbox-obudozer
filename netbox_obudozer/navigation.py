"""
Навигация плагина netbox_obudozer

Определяет структуру меню плагина в интерфейсе NetBox.
Добавляет пункты в существующее меню Virtualization.
"""
from netbox.plugins import PluginMenuButton, PluginMenuItem
from netbox.choices import ButtonColorChoices


# Добавляем пункты в раздел Virtualization
menu_items = (
    PluginMenuItem(
        link='plugins:netbox_obudozer:sync_vcenter',
        link_text='vCenter Sync',
        permissions=['virtualization.add_virtualmachine'],
        buttons=(
            PluginMenuButton(
                link='plugins:netbox_obudozer:sync_vcenter',
                title='Sync Now',
                icon_class='mdi mdi-sync',
                color=ButtonColorChoices.BLUE,
                permissions=['virtualization.add_virtualmachine']
            ),
        )
    ),
    PluginMenuItem(
        link='plugins:netbox_obudozer:businessservice_list',
        link_text='Бизнес-сервисы',
        permissions=['netbox_obudozer.view_businessservice'],
        buttons=(
            PluginMenuButton(
                link='plugins:netbox_obudozer:businessservice_add',
                title='Добавить',
                icon_class='mdi mdi-plus-thick',
                color=ButtonColorChoices.GREEN,
                permissions=['netbox_obudozer.add_businessservice']
            ),
        )
    ),
    PluginMenuItem(
        link='plugins:netbox_obudozer:servicevmassignment_list',
        link_text='Привязки VM',
        permissions=['netbox_obudozer.view_servicevmassignment'],
    ),
)
