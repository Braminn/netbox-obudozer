"""
Модели плагина netbox_obudozer

Определяет модели для хранения бизнес-услуг.
"""
from django.contrib.contenttypes.fields import GenericRelation
from django.db import models
from netbox.models import NetBoxModel
from netbox.models.features import ContactsMixin
from virtualization.models import VirtualMachine


class ObuServices(ContactsMixin, NetBoxModel):
    """
    Модель для хранения бизнес-услуг.

    Наследует от ContactsMixin для поддержки контактов и от NetBoxModel для:
    - Истории изменений (ObjectChange)
    - Поддержки тегов (tags)
    - Пользовательских полей (custom_field_data)
    - Временных меток (created, last_updated)
    - Поддержки контактов (ContactAssignment)
    """

    name = models.CharField(
        max_length=200,
        unique=True,
        verbose_name='Название услуги',
        help_text='Уникальное название услуги'
    )

    description = models.TextField(
        blank=True,
        verbose_name='Описание',
        help_text='Подробное описание услуги'
    )

    tenant = models.ForeignKey(
        to='tenancy.Tenant',
        on_delete=models.PROTECT,
        related_name='+',
        blank=True,
        null=True,
        verbose_name='Организация',
        help_text='Организация-заказчик услуги'
    )

    start_date = models.DateField(
        blank=True,
        null=True,
        verbose_name='Дата начала',
        help_text='Дата начала оказания услуги'
    )

    end_date = models.DateField(
        blank=True,
        null=True,
        verbose_name='Дата окончания',
        help_text='Дата окончания оказания услуги'
    )

    # Reverse relation для ContactAssignment (GenericForeignKey)
    contact_assignments = GenericRelation(
        to='tenancy.ContactAssignment',
        content_type_field='object_type',
        object_id_field='object_id',
        related_query_name='obuservice'
    )

    class Meta:
        ordering = ['name']
        verbose_name = 'Услуга OBU'
        verbose_name_plural = 'Услуги OBU'

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        """URL для просмотра деталей услуги."""
        from django.urls import reverse
        return reverse('plugins:netbox_obudozer:obuservices', kwargs={'pk': self.pk})


class ServiceVMAssignment(models.Model):
    """
    Промежуточная модель для связи M:N между услугами и VM.

    ВАЖНО: НЕ наследует от NetBoxModel - это стандартная промежуточная модель.
    Логирование будет происходить через изменения ObuServices.
    """

    service = models.ForeignKey(
        to='ObuServices',
        on_delete=models.CASCADE,
        related_name='vm_assignments',
        verbose_name='Услуга'
    )

    virtual_machine = models.ForeignKey(
        to='virtualization.VirtualMachine',
        on_delete=models.CASCADE,
        related_name='service_assignments',
        verbose_name='Виртуальная машина'
    )

    notes = models.TextField(
        blank=True,
        verbose_name='Примечания',
        help_text='Дополнительные примечания о назначении'
    )

    class Meta:
        ordering = ['service', 'virtual_machine']
        unique_together = ('service', 'virtual_machine')
        verbose_name = 'Назначение VM'
        verbose_name_plural = 'Назначения VM'

    def __str__(self):
        return f'{self.service.name} → {self.virtual_machine.name}'
