from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('publisher', '0003_geelark_task_status_tracking'),
    ]

    operations = [
        migrations.AlterField(
            model_name='uploadsession',
            name='status',
            field=models.CharField(
                choices=[
                    ('pending', 'Ожидает обработки'),
                    ('processing', 'Обрабатывается'),
                    ('completed', 'Завершено'),
                    ('completed_with_errors', 'Завершено с ошибками'),
                    ('failed', 'Ошибка'),
                ],
                default='pending',
                max_length=20,
            ),
        ),
    ]
