from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('publisher', '0006_publicationtask_profile_number'),
    ]

    operations = [
        migrations.AddField(
            model_name='publicationtask',
            name='geelark_started_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='publicationtask',
            name='geelark_cancel_requested_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
