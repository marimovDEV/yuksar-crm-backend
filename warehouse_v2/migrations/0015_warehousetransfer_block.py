from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('production_v2', '0015_finishedblock_height_finishedblock_length_and_more'),
        ('warehouse_v2', '0014_supplier_address_supplier_contract_expiry_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='warehousetransfer',
            name='block',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='transfers', to='production_v2.finishedblock'),
        ),
    ]
