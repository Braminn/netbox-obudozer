"""
Модели данных плагина netbox_obudozer

Содержит модель VMRecord для хранения информации о виртуальных машинах из vCenter.
"""
from django.db import models
from django.urls import reverse
from netbox.models import NetBoxModel


class VMRecord(NetBoxModel):
    """
    Модель для хранения записей о виртуальных машинах из VMware vCenter.
    
    Attributes:
        name (str): Уникальное имя виртуальной машины
        state (str): Состояние VM (running/stopped)
        vcenter_id (str): Уникальный идентификатор VM в vCenter
        exist (bool): Флаг существования VM в vCenter (False если VM была удалена)
        last_synced (datetime): Время последней синхронизации с vCenter
    
    Meta:
        ordering: Сортировка по имени
        verbose_name: Виртуальная машина
        verbose_name_plural: Виртуальные машины
    """

    name = models.CharField(
        max_length=100,
        unique=True,
        help_text="Имя виртуальной машины"
    )

    STATE_CHOICES = (
        ('running', 'Running'),
        ('stopped', 'Stopped'),
    )

    state = models.CharField(
        max_length=20,
        choices=STATE_CHOICES,
        default='stopped',
        help_text="Состояние виртуальной машины"
    )
    
    vcenter_id = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text="Уникальный идентификатор VM в vCenter (например: vm-1001)"
    )
    
    exist = models.BooleanField(
        default=True,
        help_text="Существует ли VM в vCenter (False если была удалена)"
    )
    
    last_synced = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Время последней синхронизации с vCenter"
    )

    class Meta:
        ordering = ['name']
        verbose_name = 'VM Record'
        verbose_name_plural = 'VM Records'

    def __str__(self):
        """Строковое представление объекта"""
        return self.name

    def get_absolute_url(self):
        """Возвращает URL детальной страницы VM"""
        return reverse('plugins:netbox_obudozer:vmrecord', args=[self.pk])
    
    @property
    def status_display(self):
        """Возвращает человекочитаемый статус VM"""
        if not self.exist:
            return "Not Found in vCenter"
        return self.get_state_display()
