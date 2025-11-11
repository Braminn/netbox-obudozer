"""
Формы плагина netbox_obudozer

Содержит формы для создания и редактирования VM Records.
"""
from django import forms
from netbox.forms import NetBoxModelForm
from .models import VMRecord


class VMRecordForm(NetBoxModelForm):
    """
    Форма для создания и редактирования VM Record.
    
    Включает поля: name, state, vcenter_id, exist, tags
    """
    
    class Meta:
        model = VMRecord
        fields = ['name', 'state', 'vcenter_id', 'exist', 'tags']
        help_texts = {
            'name': 'Уникальное имя виртуальной машины',
            'state': 'Текущее состояние VM',
            'vcenter_id': 'ID виртуальной машины в vCenter (опционально)',
            'exist': 'Снимите галочку, если VM была удалена из vCenter',
        }
