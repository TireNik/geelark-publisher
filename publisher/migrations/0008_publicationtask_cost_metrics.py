from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('publisher', '0007_publicationtask_timeout_tracking'),
    ]

    operations = [
        migrations.AddField(
            model_name='publicationtask',
            name='file_size_bytes',
            field=models.BigIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='publicationtask',
            name='t_download_ms',
            field=models.IntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='publicationtask',
            name='t_upload_storage_ms',
            field=models.IntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='publicationtask',
            name='t_phone_start_ms',
            field=models.IntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='publicationtask',
            name='t_create_task_ms',
            field=models.IntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='publicationtask',
            name='t_total_ms',
            field=models.IntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='publicationtask',
            name='resource_url',
            field=models.TextField(blank=True, default=''),
        ),
    ]
