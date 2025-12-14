# users/models.py
from django.db import models
from django.contrib.auth.models import AbstractUser
from django.db.models.signals import post_save
from django.conf import settings
from django.utils import timezone
from django.core.mail import send_mail
from django.template.loader import render_to_string
import random
import uuid

USER_ROLES = (
    ('client', 'Client'),
    ('trainer', 'Trainer'),
    ('admin', 'Administrator'),
)

class User(AbstractUser):
    """
    Custom user model for fitness app.
    Simpler than your ProMed model - no NPI, facility, sales rep complexity.
    """
    username = models.CharField(unique=True, max_length=255)
    email = models.EmailField(unique=True)
    full_name = models.CharField(max_length=255)
    phone_number = models.CharField(max_length=20, null=True, blank=True)
    
    # Role-based access
    role = models.CharField(max_length=50, choices=USER_ROLES, default='client')
    
    # Authentication fields
    is_verified = models.BooleanField(default=False)
    otp = models.CharField(max_length=100, null=True, blank=True)
    
    # Timestamps
    date_joined = models.DateTimeField(auto_now_add=True)
    date_updated = models.DateTimeField(auto_now=True)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username', 'full_name']

    def __str__(self):
        return f'{self.email} | {self.role}'

    def save(self, *args, **kwargs):
        if not self.username:
            self.username = self.email.split('@')[0] if '@' in self.email else self.email
        super().save(*args, **kwargs)


class Profile(models.Model):
    """
    Extended profile for additional user information.
    Keeps User model lean, profile model flexible.
    """
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    avatar = models.ImageField(
        upload_to='avatars',
        default='avatars/default_avatar.jpg',
        null=True,
        blank=True
    )
    bio = models.TextField(blank=True, null=True, max_length=500)
    
    # Trainer-specific fields
    specializations = models.CharField(max_length=255, blank=True, null=True, 
                                       help_text="e.g., 'Strength Training, HIIT, Mobility'")
    years_experience = models.IntegerField(null=True, blank=True)
    
    # Client-specific fields (for future use)
    fitness_goals = models.TextField(blank=True, null=True)
    
    date_created = models.DateTimeField(auto_now_add=True)
    date_updated = models.DateTimeField(auto_now=True)

    def __str__(self):
        return str(self.user.full_name or self.user.username)


class EmailVerificationToken(models.Model):
    """
    One-time token for email verification.
    """
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    token = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def is_expired(self):
        """Token expires after 24 hours"""
        return timezone.now() > self.created_at + timezone.timedelta(hours=24)

    def __str__(self):
        return f"Token for {self.user.email}"


class PasswordResetToken(models.Model):
    """
    One-time token for password reset.
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    token = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def is_expired(self):
        """Token expires after 30 minutes"""
        return timezone.now() > self.created_at + timezone.timedelta(minutes=30)

    def __str__(self):
        return f"Reset token for {self.user.email}"


# Signal Handlers
def create_user_profile(sender, instance, created, **kwargs):
    """Automatically create profile when user is created"""
    if created:
        Profile.objects.create(user=instance)


def send_email_verification_on_create(sender, instance, created, **kwargs):
    """
    Send verification email when user registers.
    Simplified - no admin approval needed like ProMed.
    """
    if created and not instance.is_verified:
        token, _ = EmailVerificationToken.objects.get_or_create(user=instance)
        
        # Use your frontend URL here
        verification_link = f"{settings.FRONTEND_URL}/verify-email/{token.token}"

        email_html_message = render_to_string(
            'users/email_verification.html',
            {
                'user': instance,
                'verification_link': verification_link
            }
        )
        
        send_mail(
            subject='Verify Your Email - Fitness Hub',
            message=f"Click the link to verify your email: {verification_link}",
            html_message=email_html_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[instance.email],
            fail_silently=False
        )


# Connect signals
post_save.connect(create_user_profile, sender=User)
post_save.connect(send_email_verification_on_create, sender=User)
