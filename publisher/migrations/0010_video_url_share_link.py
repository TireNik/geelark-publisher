from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('publisher', '0009_publicationtask_prepared_status'),
    ]

    operations = [
        migrations.AlterField(
            model_name='publicationtask',
            name='video_url',
            field=models.URLField(max_length=2048, verbose_name='Ссылка на видео'),
        ),
        migrations.AddField(
            model_name='publicationtask',
            name='share_link',
            field=models.TextField(blank=True, default='', verbose_name='Ссылка публикации GeeLark'),
        ),
        migrations.AddField(
            model_name='publicationtask',
            name='phone_stopped_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
