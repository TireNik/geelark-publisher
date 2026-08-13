from django.db import models


class Document(models.Model):
    """ Модель для загруженного Excel-файла """

    file = models.FileField(upload_to='excel_files/%Y/%m/%d/', verbose_name='Excel файл')
    filename = models.CharField(max_length=255, verbose_name='Исходное имя файла')
    uploaded_at = models.DateTimeField(auto_now_add=True, verbose_name='Дата загрузки')

    class Meta:
        verbose_name = 'Документ'
        verbose_name_plural = 'Документы'
        ordering = ['-uploaded_at']

    def __str__(self):
        return self.filename

class UploadSession(models.Model):
    """ Сессия загрузки файла """

    document = models.OneToOneField(
        Document,
        on_delete=models.CASCADE,
        related_name='session',
        null=True,
        blank=True
    )
    name = models.CharField(max_length=255)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(
        max_length=24,
        choices=[
            ('pending', 'Ожидает обработки'),
            ('processing', 'Обрабатывается'),
            ('completed', 'Завершено'),
            ('completed_with_errors', 'Завершено с ошибками'),
            ('failed', 'Ошибка'),
        ],
        default='pending'
    )

    class Meta:
        verbose_name = 'Сессия загрузки'
        verbose_name_plural = 'Сессии загрузки'

    def __str__(self):
        return f'Сессия {self.name}, №{self.id}'
        #return f"{self.file_name} - {self.get_status_display()}"

    @property
    def total_tasks(self):
        """ Все задачи на публикацию """
        return self.tasks.all().count() if self.tasks else 0

    @property
    def success_tasks(self):
        """ Успешные задачи на публикацию """
        return self.tasks.filter(status='success').count() if self.tasks else 0

    @property
    def error_tasks(self):
        """ Ошибочные задачи на публикацию """
        return self.tasks.filter(status='error').count() if self.tasks else 0

    @property
    def submitted_tasks(self):
        return self.tasks.filter(status__in=['prepared', 'submitted']).count() if self.tasks else 0

    @property
    def in_progress_tasks(self):
        return self.tasks.filter(status__in=['processing', 'stopping']).count() if self.tasks else 0

    @property
    def the_tasks_process(self):
        """ Выполненный процесс задач на публикацию """
        process_tasks = self.tasks.filter(status__in=['pending', 'prepared', 'processing', 'stopping', 'downloading', 'sending']).count()
        return f'Прогресс задач на публикацию: {process_tasks}/{self.tasks.all().count()}'


def refresh_session_status(session):
    """Приводит итоговый статус сессии в соответствие со статусами её задач."""
    has_unfinished_tasks = session.tasks.filter(
        status__in=['pending', 'downloading', 'sending', 'prepared', 'submitted', 'processing', 'stopping']
    ).exists()

    if has_unfinished_tasks:
        new_status = 'processing'
    elif session.tasks.filter(status='error').exists():
        new_status = 'completed_with_errors'
    elif session.status == 'failed':
        # Ошибка разбора файла остаётся отдельным техническим состоянием.
        new_status = 'failed'
    else:
        new_status = 'completed'

    if session.status != new_status:
        session.status = new_status
        session.save(update_fields=['status'])

    return new_status


class PublicationTask(models.Model):
    """ Задача на публикацию """

    session = models.ForeignKey(UploadSession, on_delete=models.CASCADE, related_name='tasks')
    profile_number = models.CharField(max_length=32, blank=True, default='', verbose_name='Номер телефона')
    profile_id = models.CharField(max_length=64, verbose_name='Номер профиля')
    social_network = models.CharField(max_length=32, verbose_name='Соцсеть')
    video_url = models.URLField(verbose_name='Ссылка на видео')
    title = models.CharField(max_length=255, blank=True, default='', verbose_name='Название видео')
    comment = models.TextField(verbose_name='Комментарий')
    publish_time = models.DateTimeField(verbose_name='Время публикации')
    status = models.CharField(
        max_length=20,
        choices=[
            ('pending', 'Ожидает'),
            ('downloading', 'Скачивается видео'),
            ('sending', 'Отправляется в Geelark'),
            ('prepared', 'Подготовлено — ждёт времени'),
            ('submitted', 'Задача отправлена в GeeLark'),
            ('processing', 'Выполняется в GeeLark'),
            ('stopping', '\u041e\u0441\u0442\u0430\u043d\u043e\u0432\u043a\u0430 \u0437\u0430\u0434\u0430\u0447\u0438 \u0432 GeeLark'),
            ('success', 'Выполнено в GeeLark'),
            ('error', 'Ошибка'),
        ],
        default='pending'
    )
    error_message = models.TextField(blank=True)
    geelark_task_id = models.CharField(max_length=128, blank=True, default='')
    geelark_status = models.PositiveSmallIntegerField(null=True, blank=True)
    geelark_fail_code = models.PositiveIntegerField(null=True, blank=True)
    geelark_checked_at = models.DateTimeField(null=True, blank=True)
    attempt_count = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    geelark_started_at = models.DateTimeField(blank=True, null=True)
    geelark_cancel_requested_at = models.DateTimeField(blank=True, null=True)

    # Метрики длительности / размера (prepare→submit; телефон стартует вне воркера)
    file_size_bytes = models.BigIntegerField(null=True, blank=True)
    t_download_ms = models.IntegerField(null=True, blank=True)
    t_upload_storage_ms = models.IntegerField(null=True, blank=True)
    t_phone_start_ms = models.IntegerField(null=True, blank=True)
    t_create_task_ms = models.IntegerField(null=True, blank=True)
    t_total_ms = models.IntegerField(null=True, blank=True)
    resource_url = models.TextField(blank=True, default='')

    class Meta:
        verbose_name = 'Задача на публикацию'
        verbose_name_plural = 'Задачи на публикацию'

    def __str__(self):
        return f"Task {self.id} Сессии {self.session.name}"
