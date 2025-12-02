from django import forms
from django.core.exceptions import ValidationError
from netbox.forms import NetBoxModelForm, NetBoxModelFilterSetForm, NetBoxModelBulkEditForm
from tenancy.models import Tenant
from virtualization.models import VirtualMachine
from utilities.forms.fields import DynamicModelChoiceField, DynamicModelMultipleChoiceField
from utilities.forms.widgets import DatePicker
from .models import BusinessService, ServiceVMAssignment


def add_blank_choice(choices):
    """
    Добавляет пустой выбор в начало списка choices.
    Используется для форм фильтрации и массового редактирования.
    """
    return [('', '---------')] + list(choices)


class BusinessServiceForm(NetBoxModelForm):
    """
    Форма для создания и редактирования бизнес-сервиса.
    """
    organization = DynamicModelChoiceField(
        queryset=Tenant.objects.all(),
        label='Организация',
        help_text='Клиент/организация'
    )

    class Meta:
        model = BusinessService
        fields = [
            'name', 'organization', 'status', 'contract_start_date',
            'contract_end_date', 'request_number', 'responsible_person',
            'description', 'tags'
        ]
        widgets = {
            'contract_start_date': DatePicker(),
            'contract_end_date': DatePicker(),
            'description': forms.Textarea(attrs={'rows': 3}),
        }

    def clean(self):
        cleaned_data = super().clean()

        contract_start = cleaned_data.get('contract_start_date')
        contract_end = cleaned_data.get('contract_end_date')

        # Валидация дат договора
        if contract_start and contract_end:
            if contract_end < contract_start:
                raise ValidationError({
                    'contract_end_date': 'Дата окончания не может быть раньше даты начала договора'
                })

        return cleaned_data


class BusinessServiceFilterForm(NetBoxModelFilterSetForm):
    """
    Форма для фильтрации списка бизнес-сервисов.
    """
    model = BusinessService
    fieldsets = (
        (None, {'fields': ('q', 'filter_id', 'tag')}),
        ('Атрибуты', {'fields': ('organization_id', 'status', 'responsible_person')}),
        ('Даты договора', {'fields': ('contract_start_date_after', 'contract_start_date_before',
                                      'contract_end_date_after', 'contract_end_date_before')}),
    )

    organization_id = DynamicModelMultipleChoiceField(
        queryset=Tenant.objects.all(),
        required=False,
        label='Организация'
    )

    status = forms.MultipleChoiceField(
        choices=add_blank_choice(BusinessService.StatusChoices),
        required=False,
        label='Статус'
    )

    responsible_person = forms.CharField(
        required=False,
        label='Ответственное лицо'
    )

    contract_start_date_after = forms.DateField(
        required=False,
        label='Договор с (от)',
        widget=DatePicker()
    )

    contract_start_date_before = forms.DateField(
        required=False,
        label='Договор с (до)',
        widget=DatePicker()
    )

    contract_end_date_after = forms.DateField(
        required=False,
        label='Договор до (от)',
        widget=DatePicker()
    )

    contract_end_date_before = forms.DateField(
        required=False,
        label='Договор до (до)',
        widget=DatePicker()
    )


class BusinessServiceBulkEditForm(NetBoxModelBulkEditForm):
    """
    Форма для массового редактирования бизнес-сервисов.
    """
    model = BusinessService

    status = forms.ChoiceField(
        choices=add_blank_choice(BusinessService.StatusChoices),
        required=False,
        label='Статус'
    )

    responsible_person = forms.CharField(
        max_length=200,
        required=False,
        label='Ответственное лицо'
    )

    contract_end_date = forms.DateField(
        required=False,
        widget=DatePicker(),
        label='Дата окончания договора'
    )

    description = forms.CharField(
        max_length=500,
        required=False,
        widget=forms.Textarea(attrs={'rows': 3}),
        label='Описание'
    )

    nullable_fields = ['contract_end_date', 'description', 'request_number']


class ServiceVMAssignmentForm(NetBoxModelForm):
    """
    Форма для привязки VM к бизнес-сервису.
    """
    service = DynamicModelChoiceField(
        queryset=BusinessService.objects.all(),
        label='Бизнес-сервис',
        help_text='Выберите сервис'
    )

    virtual_machine = DynamicModelChoiceField(
        queryset=VirtualMachine.objects.all(),
        label='Виртуальная машина',
        help_text='Выберите VM'
    )

    class Meta:
        model = ServiceVMAssignment
        fields = ['service', 'virtual_machine', 'notes']
        widgets = {
            'notes': forms.Textarea(attrs={'rows': 3}),
        }

    def clean(self):
        cleaned_data = super().clean()

        service = cleaned_data.get('service')
        vm = cleaned_data.get('virtual_machine')

        # Проверка на дублирование привязки
        if service and vm:
            # Исключаем текущий объект при редактировании
            qs = ServiceVMAssignment.objects.filter(
                service=service,
                virtual_machine=vm
            )
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)

            if qs.exists():
                raise ValidationError(
                    'Эта виртуальная машина уже привязана к данному сервису'
                )

        return cleaned_data
