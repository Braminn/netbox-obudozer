# Generated migration to remove VMRecord model
# Migration from custom VMRecord to NetBox built-in VirtualMachine model

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('netbox_obudozer', '0002_vmrecord_exist_vmrecord_last_synced_and_more'),
    ]

    operations = [
        # Delete VMRecord model - data will be repopulated on first sync
        migrations.DeleteModel(
            name='VMRecord',
        ),
    ]
