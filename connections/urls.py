# connections/urls.py

from django.urls import path
from . import views

app_name = 'connections'

urlpatterns = [
    # Trainer Discovery
    path('trainers/', views.TrainerListView.as_view(), name='trainer-list'),
    path('trainers/<int:pk>/', views.TrainerDetailView.as_view(), name='trainer-detail'),

    # Connection Management
    path('request/', views.request_trainer_connection, name='request-connection'),
    path('<int:connection_id>/accept/', views.accept_connection_request, name='accept-connection'),
    path('<int:connection_id>/reject/', views.reject_connection_request, name='reject-connection'),
    path('my-connections/', views.my_connections, name='my-connections'),
    path('<int:connection_id>/permissions/', views.update_connection_permissions, name='update-permissions'),
    path('<int:connection_id>/end/', views.end_connection, name='end-connection'),
]