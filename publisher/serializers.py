from rest_framework import serializers
from .models import Document, UploadSession, PublicationTask


class DocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Document
        fields = ['id', 'filename', 'uploaded_at']


class UploadSessionSerializer(serializers.ModelSerializer):
    document = DocumentSerializer(read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    total_tasks = serializers.IntegerField(read_only=True)
    success_tasks = serializers.IntegerField(read_only=True)
    error_tasks = serializers.IntegerField(read_only=True)

    class Meta:
        model = UploadSession
        fields = [
            'id',
            'document',
            'name',
            'uploaded_at',
            'status',
            'status_display',
            'total_tasks',
            'success_tasks',
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
            'profile_id',
            'social_network',
            'video_url',
            #'title',
            'comment',
            'publish_time',
            'publish_time_formatted',
            'status',
            'status_display',
            'error_message',
            'created_at',
            'processed_at'
        ]


class ExcelUploadSerializer(serializers.Serializer):
    excel_file = serializers.FileField()

    def validate_excel_file(self, value):
        """Проверка расширения файла"""
        if not value.name.endswith(('.xlsx', '.xls')):
            raise serializers.ValidationError("Файл должен быть Excel (.xlsx или .xls)")
        return value