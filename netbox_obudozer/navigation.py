"""
Навигационное меню плагина netbox_obudozer

Использует PluginMenu для группировки пунктов меню (NetBox 4.0+ подход).
"""
from netbox.plugins import PluginMenu, PluginMenuButton, PluginMenuItem
from netbox.choices import ButtonColorChoices


# Группировка пунктов меню по категориям
menu = PluginMenu(
    label='Obudozer',
    groups=(
        ('Услуги', (
            PluginMenuItem(
                link='plugins:netbox_obudozer:obuservices_list',
                link_text='Услуги OBU',
                permissions=['netbox_obudozer.view_obuservices'],
                buttons=(
                    PluginMenuButton(
                        link='plugins:netbox_obudozer:obuservices_add',
                        title='Добавить',
                        icon_class='mdi mdi-plus-thick',
                        color=ButtonColorChoices.GREEN,
                        permissions=['netbox_obudozer.add_obuservices']
                    ),
                )
            ),
        )),
        ('vCenter', (
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
        )),
    ),
    icon_class='mdi mdi-briefcase'
)
