from django.contrib import admin
from .models import UploadSession, PublicationTask, Document


@admin.register(UploadSession)
class UploadSessionAdmin(admin.ModelAdmin):
    list_display = ['id', 'name', 'status', 'uploaded_at']
    list_filter = ['status', 'uploaded_at']
    readonly_fields = ['uploaded_at']


@admin.register(PublicationTask)
class PublicationTaskAdmin(admin.ModelAdmin):
    list_display = ['id', 'session', 'profile_id', 'social_network', 'status', 'publish_time']
    list_filter = ['status', 'social_network']
    search_fields = ['profile_id']


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ['id', 'filename', 'uploaded_at']
    list_filter = ['uploaded_at']