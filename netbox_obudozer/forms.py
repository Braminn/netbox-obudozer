"""
Формы для плагина netbox_obudozer

Определяет формы для редактирования моделей.
"""
from django import forms
from netbox.forms import NetBoxModelForm, NetBoxModelBulkEditForm
from utilities.forms.fields import CommentField, DynamicModelChoiceField, DynamicModelMultipleChoiceField, DatePicker
from virtualization.models import VirtualMachine
from tenancy.models import Tenant
from .models import ObuServices, ServiceVMAssignment


class ObuServicesForm(NetBoxModelForm):
    """
    Форма для создания и редактирования услуг OBU с мультиселектом VM.

    Наследует от NetBoxModelForm для автоматического получения:
    - Поддержки пользовательских полей (custom fields)
    - Поддержки тегов (tags)
    - Стилизации Bootstrap/NetBox
    """

    tenant = DynamicModelChoiceField(
        queryset=Tenant.objects.all(),
        required=False,
        label='Организация'
    )

    start_date = DatePicker(
        required=False,
        label='Дата начала'
    )

    end_date = DatePicker(
        required=False,
        label='Дата окончания'
    )

    virtual_machines = DynamicModelMultipleChoiceField(
        queryset=VirtualMachine.objects.all(),
        required=False,
        label='Виртуальные машины',
        query_params={'status': 'active'}  # Только активные VM
    )

    class Meta:
        model = ObuServices
        fields = [
            'name',
            'description',
            'tenant',
            'start_date',
            'end_date',
            'virtual_machines',
            'tags',
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # При редактировании - показать уже назначенные VM
        if self.instance and self.instance.pk:
            assigned_vms = VirtualMachine.objects.filter(
                service_assignments__service=self.instance
            )
            self.initial['virtual_machines'] = assigned_vms

    def save(self, commit=True):
        """
        Сохранение с обработкой M2M через промежуточную модель.

        ВАЖНО: Для минималистичного решения допустимо переопределить save(),
        но для более сложных случаев лучше использовать сигналы.
        """
        instance = super().save(commit=commit)

        if commit:
            # Удалить старые назначения
            instance.vm_assignments.all().delete()

            # Создать новые назначения
            for vm in self.cleaned_data.get('virtual_machines', []):
                ServiceVMAssignment.objects.create(
                    service=instance,
                    virtual_machine=vm
                )

        return instance


class ObuServicesBulkEditForm(NetBoxModelBulkEditForm):
    """
    Форма для массового редактирования услуг OBU.

    NetBoxModelBulkEditForm автоматически обрабатывает:
    - Добавление/удаление тегов
    - Обновление custom fields
    - Комментарии к изменениям
    """
    tenant = DynamicModelChoiceField(
        queryset=Tenant.objects.all(),
        required=False
    )
    start_date = DatePicker(
        required=False
    )
    end_date = DatePicker(
        required=False
    )
    description = forms.CharField(
        max_length=500,
        required=False,
        widget=forms.Textarea(attrs={'rows': 3})
    )
    comments = CommentField()

    model = ObuServices
    nullable_fields = ['description', 'tenant', 'start_date', 'end_date']
