from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('publisher', '0001_initial'),
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
                    ('success', 'Успешно'),
                    ('error', 'Ошибка'),
                ],
                default='pending',
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name='publicationtask',
            name='title',
            field=models.CharField(blank=True, default='', max_length=255, verbose_name='Название видео'),
        ),
        migrations.AddField(
            model_name='publicationtask',
            name='attempt_count',
            field=models.PositiveSmallIntegerField(default=0),
        ),
        migrations.AddField(
            model_name='publicationtask',
            name='geelark_task_id',
            field=models.CharField(blank=True, default='', max_length=128),
        ),
    ]
