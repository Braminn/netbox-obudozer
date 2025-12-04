"""
Формы для плагина netbox_obudozer

Определяет формы для редактирования моделей.
"""
from django import forms
from netbox.forms import NetBoxModelForm, NetBoxModelBulkEditForm
from utilities.forms.fields import CommentField
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


class ObuServicesBulkEditForm(NetBoxModelBulkEditForm):
    """
    Форма для массового редактирования услуг OBU.

    NetBoxModelBulkEditForm автоматически обрабатывает:
    - Добавление/удаление тегов
    - Обновление custom fields
    - Комментарии к изменениям
    """
    description = forms.CharField(
        max_length=500,
        required=False,
        widget=forms.Textarea(attrs={'rows': 3})
    )
    comments = CommentField()

    model = ObuServices
    nullable_fields = ['description']
