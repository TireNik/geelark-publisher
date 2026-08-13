from rest_framework import serializers
from .models import Document, UploadSession, PublicationTask


class DocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Document
        fields = ['id', 'filename', 'uploaded_at']


class UploadSessionSerializer(serializers.ModelSerializer):
    document = DocumentSerializer(read_only=True)
    file_name = serializers.SerializerMethodField()
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    total_tasks = serializers.IntegerField(read_only=True)
    success_tasks = serializers.IntegerField(read_only=True)
    submitted_tasks = serializers.IntegerField(read_only=True)
    in_progress_tasks = serializers.IntegerField(read_only=True)
    error_tasks = serializers.IntegerField(read_only=True)

    def get_file_name(self, obj):
        return obj.document.filename if obj.document_id else ''

    class Meta:
        model = UploadSession
        fields = [
            'id',
            'document',
            'file_name',
            'name',
            'uploaded_at',
            'status',
            'status_display',
            'total_tasks',
            'success_tasks',
            'submitted_tasks',
            'in_progress_tasks',
            'error_tasks',
        ]


class PublicationTaskSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    publish_time_formatted = serializers.DateTimeField(
        source='publish_time',
        format='%d.%m.%Y %H:%M',
        read_only=True
    )

    class Meta:
        model = PublicationTask
        fields = [
            'id',
            'session',
            'profile_number',
            'profile_id',
            'social_network',
            'video_url',
            'title',
            'comment',
            'publish_time',
            'publish_time_formatted',
            'status',
            'status_display',
            'error_message',
            'geelark_task_id',
            'geelark_status',
            'geelark_fail_code',
            'geelark_checked_at',
            'geelark_cancel_requested_at',
            'geelark_started_at',
            'attempt_count',
            'created_at',
            'processed_at',
            'file_size_bytes',
            't_download_ms',
            't_upload_storage_ms',
            't_phone_start_ms',
            't_create_task_ms',
            't_total_ms',
        ]


class ExcelUploadSerializer(serializers.Serializer):
    excel_file = serializers.FileField()

    def validate_excel_file(self, value):
        """Проверка расширения файла"""
        if not value.name.endswith(('.xlsx', '.xls')):
            raise serializers.ValidationError("Файл должен быть Excel (.xlsx или .xls)")
        return value
