from django.db import models
from django.urls import reverse
from django.core.exceptions import ValidationError
from netbox.models import NetBoxModel
from tenancy.models import Tenant


class BusinessService(NetBoxModel):
    """
    Представляет бизнес-услугу, предоставляемую клиенту/организации.
    Отслеживает договорные и операционные детали услуг.
    """

    class StatusChoices(models.TextChoices):
        ACTIVE = 'active', 'Активен'
        SUSPENDED = 'suspended', 'Приостановлен'
        TERMINATED = 'terminated', 'Завершен'

    # Основная информация
    name = models.CharField(
        max_length=200,
        verbose_name='Название сервиса',
        help_text='Наименование бизнес-сервиса'
    )

    # Клиент/Организация - связь с NetBox Tenant
    organization = models.ForeignKey(
        to=Tenant,
        on_delete=models.PROTECT,
        related_name='business_services',
        verbose_name='Организация',
        help_text='Клиент/организация, которой предоставляется сервис'
    )

    # Информация о договоре
    contract_start_date = models.DateField(
        verbose_name='Дата заключения договора',
        help_text='Дата начала действия договора'
    )

    contract_end_date = models.DateField(
        blank=True,
        null=True,
        verbose_name='Дата окончания договора',
        help_text='Дата окончания договора (для отслеживания необходимости удаления VM)'
    )

    request_number = models.CharField(
        max_length=100,
        blank=True,
        verbose_name='Номер заявки',
        help_text='Номер заявки/тикета на создание сервиса'
    )

    # Ответственное лицо
    responsible_person = models.CharField(
        max_length=200,
        verbose_name='Ответственное лицо',
        help_text='Ответственное лицо с нашей стороны'
    )

    # Описание
    description = models.TextField(
        blank=True,
        verbose_name='Описание',
        help_text='Дополнительное описание сервиса'
    )

    # Статус
    status = models.CharField(
        max_length=20,
        choices=StatusChoices.choices,
        default=StatusChoices.ACTIVE,
        verbose_name='Статус'
    )

    class Meta:
        ordering = ['name']
        verbose_name = 'Бизнес-сервис'
        verbose_name_plural = 'Бизнес-сервисы'

    def __str__(self):
        return f"{self.name} ({self.organization})"

    def get_absolute_url(self):
        return reverse('plugins:netbox_obudozer:businessservice', args=[self.pk])

    def get_status_class(self):
        """
        Возвращает CSS класс для badge в зависимости от статуса.
        """
        status_classes = {
            self.StatusChoices.ACTIVE: 'success',
            self.StatusChoices.SUSPENDED: 'warning',
            self.StatusChoices.TERMINATED: 'danger',
        }
        return status_classes.get(self.status, 'secondary')

    def clean(self):
        """
        Валидация модели: дата окончания не может быть раньше даты начала.
        """
        super().clean()

        if self.contract_start_date and self.contract_end_date:
            if self.contract_end_date < self.contract_start_date:
                raise ValidationError({
                    'contract_end_date': 'Дата окончания договора не может быть раньше даты начала'
                })


class ServiceVMAssignment(models.Model):
    """
    Промежуточная модель для связи BusinessService и VirtualMachine.
    Позволяет отслеживать, когда VM была назначена на сервис, и добавлять метаданные.
    """

    service = models.ForeignKey(
        to='BusinessService',
        on_delete=models.CASCADE,
        related_name='vm_assignments',
        verbose_name='Сервис'
    )

    virtual_machine = models.ForeignKey(
        to='virtualization.VirtualMachine',
        on_delete=models.CASCADE,
        related_name='service_assignments',
        verbose_name='Виртуальная машина'
    )

    assigned_date = models.DateField(
        auto_now_add=True,
        verbose_name='Дата назначения',
        help_text='Дата назначения VM на сервис'
    )

    notes = models.TextField(
        blank=True,
        verbose_name='Примечания',
        help_text='Дополнительные заметки о назначении'
    )

    class Meta:
        ordering = ['service', 'virtual_machine']
        unique_together = [['service', 'virtual_machine']]
        verbose_name = 'Привязка VM к сервису'
        verbose_name_plural = 'Привязки VM к сервисам'

    def __str__(self):
        return f"{self.service.name} → {self.virtual_machine.name}"

    def get_absolute_url(self):
        return self.service.get_absolute_url()
