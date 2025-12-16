# workouts/urls.py
from django.urls import path
from . import views

app_name = 'workouts'

urlpatterns = [
    # Exercise Library
    path('exercises/', views.ExerciseListCreateView.as_view(), name='exercise-list-create'),
    path('exercises/<int:pk>/', views.ExerciseDetailView.as_view(), name='exercise-detail'),

    # Workout Logs
    path('workouts/', views.WorkoutLogListView.as_view(), name='workout-list'),
    path('workouts/<int:pk>/', views.WorkoutLogDetailView.as_view(), name='workout-detail'),
    path('workouts/create/', views.WorkoutLogCreateView.as_view(), name='workout-create'),
    path('workouts/<int:pk>/update/', views.WorkoutLogUpdateView.as_view(), name='workout-update'),
    path('workouts/<int:pk>/delete/', views.WorkoutLogDeleteView.as_view(), name='workout-delete'),
    path('workouts/<int:pk>/favorite/', views.toggle_favorite, name='workout-toggle-favorite'),
    path('workouts/copy/', views.copy_workout, name='workout-copy'),

    # Analytics & Stats
    path('stats/', views.workout_stats, name='workout-stats'),
    path('personal-records/', views.personal_records, name='personal-records'),

    # AI Workout Generation
    path('ai/generate/', views.generate_ai_workout_view, name='ai-generate-workout'),
    path('ai/save/', views.save_ai_workout, name='ai-save-workout'),
]