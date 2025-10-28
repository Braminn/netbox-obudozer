from django import forms
from netbox.forms import NetBoxModelForm
from .models import VMRecord


class VMRecordForm(NetBoxModelForm):
    """Форма для создания и редактирования VM записей"""

    class Meta:
        model = VMRecord
        fields = ['name', 'state', 'tags']
