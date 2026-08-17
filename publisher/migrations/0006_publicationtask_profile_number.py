import openpyxl

from django.db import migrations, models


def backfill_profile_numbers(apps, schema_editor):
    PublicationTask = apps.get_model('publisher', 'PublicationTask')
    UploadSession = apps.get_model('publisher', 'UploadSession')

    # Старые версии сервиса иногда сохраняли в profile_id запись вида
    # «30 / 629...». Сначала разделяем её прямо в базе.
    for task in PublicationTask.objects.filter(profile_id__contains='/'):
        profile_number, technical_id = task.profile_id.split('/', 1)
        task.profile_number = profile_number.strip()
        task.profile_id = technical_id.strip()
        task.save(update_fields=['profile_number', 'profile_id'])

    # В актуальных старых записях остался только ID GeeLark, но исходный Excel
    # сохранён у сессии. Восстанавливаем номер телефона из первого столбца.
    for session in UploadSession.objects.exclude(document=None):
        try:
            with session.document.file.open('rb') as excel_file:
                worksheet = openpyxl.load_workbook(excel_file, read_only=True).active
                numbers_by_profile_id = {}
                for row in worksheet.iter_rows(min_row=2, values_only=True):
                    profile_reference = row[0] if row else None
                    if profile_reference is None:
                        continue
                    raw_reference = str(profile_reference).strip()
                    if '/' not in raw_reference:
                        continue
                    profile_number, technical_id = raw_reference.split('/', 1)
                    numbers_by_profile_id[technical_id.strip()] = profile_number.strip()
        except Exception:
            continue

        for task in PublicationTask.objects.filter(session_id=session.id, profile_number=''):
            profile_number = numbers_by_profile_id.get(task.profile_id)
            if profile_number:
                task.profile_number = profile_number
                task.save(update_fields=['profile_number'])


class Migration(migrations.Migration):

    dependencies = [
        ('publisher', '0005_uploadsession_status_max_length'),
    ]

    operations = [
        migrations.AddField(
            model_name='publicationtask',
            name='profile_number',
            field=models.CharField(blank=True, default='', max_length=32, verbose_name='Номер телефона'),
        ),
        migrations.RunPython(backfill_profile_numbers, migrations.RunPython.noop),
    ]
