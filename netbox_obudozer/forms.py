"""
Формы для плагина netbox_obudozer

Определяет формы для редактирования моделей.
"""
from netbox.forms import NetBoxModelForm
from .models import ObuServices


class ObuServicesForm(NetBoxModelForm):
    """
    Форма для создания и редактирования услуг OBU.

    Наследует от NetBoxModelForm для автоматического получения:
    - Поддержки пользовательских полей (custom fields)
    - Поддержки тегов (tags)
    - Стилизации Bootstrap/NetBox
    """

    class Meta:
        model = ObuServices
        fields = [
            'name',
            'description',
            'tags',
        ]
