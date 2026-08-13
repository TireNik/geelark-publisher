from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('publisher', '0008_publicationtask_cost_metrics'),
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
                    ('prepared', 'Подготовлено — ждёт времени'),
                    ('submitted', 'Задача отправлена в GeeLark'),
                    ('processing', 'Выполняется в GeeLark'),
                    ('stopping', 'Остановка задачи в GeeLark'),
                    ('success', 'Выполнено в GeeLark'),
                    ('error', 'Ошибка'),
                ],
                default='pending',
                max_length=20,
                verbose_name='Статус',
            ),
        ),
    ]