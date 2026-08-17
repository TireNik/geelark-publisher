from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('publisher', '0002_publicationtask_delivery_tracking'),
    ]

    operations = [
        migrations.AlterField(
            model_name='publicationtask',
            name='status',
            field=models.CharField(
                choices=[
                    ('pending', 'Ожидает'),
                    ('downloading', 'Скачивается видео'),
                    ('sending', 'Отправляется в Geelark'),
                    ('submitted', 'Задача отправлена в GeeLark'),
                    ('processing', 'Выполняется в GeeLark'),
                    ('success', 'Выполнено в GeeLark'),
                    ('error', 'Ошибка'),
                ],
                default='pending',
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name='publicationtask',
            name='geelark_checked_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='publicationtask',
            name='geelark_fail_code',
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='publicationtask',
            name='geelark_status',
            field=models.PositiveSmallIntegerField(blank=True, null=True),
        ),
    ]
