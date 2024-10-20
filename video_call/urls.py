from django.urls import path
from . import views

app_name = 'video_call'
urlpatterns = [
    path('', views.IndexView.as_view(), name='index'),
    path('call_line_process/', views.callLineProcess, name='call_line_process'),
]
