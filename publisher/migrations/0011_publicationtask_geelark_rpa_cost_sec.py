from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('publisher', '0010_video_url_share_link'),
    ]

    operations = [
        migrations.AddField(
            model_name='publicationtask',
            name='geelark_rpa_cost_sec',
            field=models.IntegerField(
                blank=True,
                null=True,
                verbose_name='GeeLark task/query.cost (секунды RPA)',
            ),
        ),
    ]
