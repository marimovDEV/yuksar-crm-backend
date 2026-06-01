from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('production_v2', '0015_finishedblock_height_finishedblock_length_and_more'),
        ('transactions', '0005_transaction_batch_transaction_document_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='transaction',
            name='block',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='transactions', to='production_v2.finishedblock'),
        ),
    ]
