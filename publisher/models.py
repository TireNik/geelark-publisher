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
        max_length=20,
        choices=[
            ('pending', 'Ожидает обработки'),
            ('processing', 'Обрабатывается'),
            ('completed', 'Завершено'),
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
        return self.tasks.filter(status='submitted').count() if self.tasks else 0

    @property
    def in_progress_tasks(self):
        return self.tasks.filter(status='processing').count() if self.tasks else 0

    @property
    def the_tasks_process(self):
        """ Выполненный процесс задач на публикацию """
        process_tasks = self.tasks.filter(status__in=['pending', 'processing', 'downloading', 'sending']).count()
        return f'Прогресс задач на публикацию: {process_tasks}/{self.tasks.all().count()}'


class PublicationTask(models.Model):
    """ Задача на публикацию """

    session = models.ForeignKey(UploadSession, on_delete=models.CASCADE, related_name='tasks')
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
            ('submitted', 'Задача отправлена в GeeLark'),
            ('processing', 'Выполняется в GeeLark'),
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

    class Meta:
        verbose_name = 'Задача на публикацию'
        verbose_name_plural = 'Задачи на публикацию'

    def __str__(self):
        return f"Task {self.id} Сессии {self.session.name}"
