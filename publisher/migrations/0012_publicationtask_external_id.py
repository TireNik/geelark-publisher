from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('publisher', '0011_publicationtask_geelark_rpa_cost_sec'),
    ]

    operations = [
        migrations.AddField(
            model_name='publicationtask',
            name='external_id',
            field=models.CharField(
                blank=True,
                default='',
                max_length=64,
                verbose_name='Внешний id (vf-entry-…)',
            ),
        ),
    ]
