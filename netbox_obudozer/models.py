from django.db import models
from django.urls import reverse
from netbox.models import NetBoxModel


class VMRecord(NetBoxModel):
    """Модель для хранения записей о виртуальных машинах"""

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

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse('plugins:netbox_obudozer:vmrecord', args=[self.pk])
