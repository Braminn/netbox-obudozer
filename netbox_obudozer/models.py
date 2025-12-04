"""
Модели плагина netbox_obudozer

Определяет модели для хранения бизнес-услуг.
"""
from django.db import models
from netbox.models import NetBoxModel


class ObuServices(NetBoxModel):
    """
    Модель для хранения бизнес-услуг.

    Наследует от NetBoxModel для автоматического получения:
    - Истории изменений (ObjectChange)
    - Поддержки тегов (tags)
    - Пользовательских полей (custom_field_data)
    - Временных меток (created, last_updated)
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
