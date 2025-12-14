# users/urls.py
from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from . import views

app_name = 'users'

urlpatterns = [
    # Authentication
    path('token/', views.MyTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('register/', views.RegisterUser.as_view(), name='register'),
    
    # Email Verification
    path('verify-email/<uuid:token>/', views.VerifyEmailView.as_view(), name='verify-email'),
    path('resend-verification/', views.ResendVerificationEmail.as_view(), name='resend-verification'),
    
    # Password Reset
    path('request-password-reset/', views.RequestPasswordResetView.as_view(), name='request-password-reset'),
    path('reset-password/<uuid:token>/', views.ResetPasswordView.as_view(), name='reset-password'),
    
    # Profile
    path('profile/', views.ProfileView.as_view(), name='profile'),
]