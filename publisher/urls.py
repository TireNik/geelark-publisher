from django.urls import path
from . import views

app_name = 'publisher'

urlpatterns = [
    # API endpoints (для данных)
    path('api/upload/', views.ExcelUploadView.as_view(), name='api_upload'),
    path('api/status/<int:session_id>/', views.TaskStatusAPIView.as_view(), name='api_status'),
    path('api/sessions/', views.SessionsListAPIView.as_view(), name='api_sessions'),
    #path('api/process/<int:session_id>/', views.ProcessTaskAPIView.as_view(), name='api_process'),

    # HTML страницы (только отдают шаблон, данные через API)
    path('', views.upload_page, name='upload_page'),
    path('status/<int:session_id>/', views.status_page, name='status_page'),
]