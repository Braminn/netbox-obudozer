# Generated migration for netbox_obudozer plugin
# Creates BusinessService and ServiceVMAssignment models

from django.db import migrations, models
import django.db.models.deletion
import taggit.managers
import utilities.json


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('tenancy', '0013_contactassignment_rename_content_type'),
        ('virtualization', '0040_virtualmachine_config_template'),
        ('extras', '0115_convert_dashboard_widgets'),
    ]

    operations = [
        migrations.CreateModel(
            name='BusinessService',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ('created', models.DateTimeField(auto_now_add=True, null=True)),
                ('last_updated', models.DateTimeField(auto_now=True, null=True)),
                ('custom_field_data', models.JSONField(blank=True, default=dict, encoder=utilities.json.CustomFieldJSONEncoder)),
                ('description', models.TextField(blank=True, verbose_name='Описание')),
                ('comments', models.TextField(blank=True)),
                ('name', models.CharField(max_length=200, verbose_name='Название сервиса')),
                ('contract_start_date', models.DateField(verbose_name='Дата заключения договора')),
                ('contract_end_date', models.DateField(blank=True, null=True, verbose_name='Дата окончания договора')),
                ('request_number', models.CharField(blank=True, max_length=100, verbose_name='Номер заявки')),
                ('responsible_person', models.CharField(max_length=200, verbose_name='Ответственное лицо')),
                ('status', models.CharField(
                    choices=[('active', 'Активен'), ('suspended', 'Приостановлен'), ('terminated', 'Завершен')],
                    default='active',
                    max_length=20,
                    verbose_name='Статус'
                )),
                ('organization', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='business_services',
                    to='tenancy.tenant',
                    verbose_name='Организация'
                )),
                ('tags', taggit.managers.TaggableManager(through='extras.TaggedItem', to='extras.Tag')),
            ],
            options={
                'verbose_name': 'Бизнес-сервис',
                'verbose_name_plural': 'Бизнес-сервисы',
                'ordering': ['name'],
            },
        ),
        migrations.CreateModel(
            name='ServiceVMAssignment',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ('assigned_date', models.DateField(auto_now_add=True, verbose_name='Дата назначения')),
                ('notes', models.TextField(blank=True, verbose_name='Примечания')),
                ('service', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='vm_assignments',
                    to='netbox_obudozer.businessservice',
                    verbose_name='Сервис'
                )),
                ('virtual_machine', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='service_assignments',
                    to='virtualization.virtualmachine',
                    verbose_name='Виртуальная машина'
                )),
            ],
            options={
                'verbose_name': 'Привязка VM к сервису',
                'verbose_name_plural': 'Привязки VM к сервисам',
                'ordering': ['service', 'virtual_machine'],
            },
        ),
        migrations.AddConstraint(
            model_name='servicevmassignment',
            constraint=models.UniqueConstraint(
                fields=['service', 'virtual_machine'],
                name='unique_service_vm'
            ),
        ),
    ]
