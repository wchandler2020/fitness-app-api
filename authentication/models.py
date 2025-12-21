# authentication/models.py

from django.db import models
from django.contrib.auth.models import AbstractUser
from django.db.models.signals import post_save
from django.conf import settings
from django.utils import timezone
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.core.exceptions import ValidationError
import uuid

USER_ROLES = (
    ('client', 'Client'),
    ('trainer', 'Trainer'),
    ('admin', 'Administrator'),
)


class User(AbstractUser):
    """Custom user model for fitness app."""
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
    Universal profile for all users (clients and trainers).
    Fields are conditionally required based on user role.
    """
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')

    # === UNIVERSAL FIELDS (ALL USERS) ===
    avatar = models.ImageField(
        upload_to='avatars/%Y/%m/',
        default='avatars/default_avatar.jpg',
        null=True,
        blank=True
    )
    bio = models.TextField(
        blank=True,
        null=True,
        max_length=1000,
        help_text="Tell us about yourself"
    )

    # === LOCATION (ALL USERS - but critical for trainers) ===
    city = models.CharField(max_length=100, blank=True)
    state = models.CharField(max_length=50, blank=True)
    zip_code = models.CharField(max_length=10, blank=True)
    country = models.CharField(max_length=50, default='USA')

    # Geographic coordinates for distance-based search
    latitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
        help_text="Auto-populated from address"
    )
    longitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
        help_text="Auto-populated from address"
    )

    # === PERSONAL INFO (OPTIONAL FOR ALL) ===
    gender = models.CharField(
        max_length=20,
        choices=[
            ('male', 'Male'),
            ('female', 'Female'),
            ('non_binary', 'Non-Binary'),
            ('prefer_not_to_say', 'Prefer Not to Say'),
        ],
        blank=True
    )
    date_of_birth = models.DateField(
        null=True,
        blank=True,
        help_text="Used to calculate age (optional)"
    )

    # === SOCIAL LINKS (ALL USERS) ===
    instagram_handle = models.CharField(max_length=100, blank=True)
    website_url = models.URLField(blank=True)

    # === TRAINER-SPECIFIC FIELDS ===
    # Professional Info
    specializations = models.JSONField(
        default=list,
        blank=True,
        help_text='["Strength Training", "HIIT", "Weight Loss", "Sports Performance"]'
    )
    certifications = models.JSONField(
        default=list,
        blank=True,
        help_text='[{"name": "NASM-CPT", "issuer": "NASM", "year": 2020, "number": "12345"}]'
    )
    years_experience = models.IntegerField(
        null=True,
        blank=True,
        help_text="Years as a professional trainer"
    )
    education = models.TextField(
        blank=True,
        help_text="Degrees, relevant education, etc."
    )

    # Service Offerings
    offers_in_person = models.BooleanField(
        default=True,
        help_text="Offers in-person training sessions"
    )
    offers_virtual = models.BooleanField(
        default=False,
        help_text="Offers online/video training sessions"
    )
    offers_home_visits = models.BooleanField(
        default=False,
        help_text="Will travel to client's home/location"
    )
    offers_gym_sessions = models.BooleanField(
        default=True,
        help_text="Trains clients at a gym"
    )
    preferred_gym_name = models.CharField(
        max_length=200,
        blank=True,
        help_text="Primary gym location (e.g., 'LA Fitness on Main St')"
    )
    service_radius = models.IntegerField(
        null=True,
        blank=True,
        help_text="Miles willing to travel for in-person sessions"
    )

    # Pricing (for trainers)
    hourly_rate = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Standard hourly rate in USD"
    )
    package_pricing = models.JSONField(
        default=dict,
        blank=True,
        help_text='{"5_sessions": 250, "10_sessions": 450, "20_sessions": 850}'
    )

    # Availability (for trainers)
    is_accepting_clients = models.BooleanField(
        default=True,
        help_text="Currently accepting new clients"
    )
    max_clients = models.IntegerField(
        null=True,
        blank=True,
        default=20,
        help_text="Maximum number of active clients"
    )

    # Contact (trainers can have public contact info)
    contact_phone = models.CharField(
        max_length=20,
        blank=True,
        help_text="Public phone number (if different from account)"
    )
    contact_email = models.EmailField(
        blank=True,
        help_text="Public email (if different from account email)"
    )

    # === MARKETPLACE FEATURES (TRAINERS ONLY) ===
    # Subscription & Listing
    subscription_tier = models.CharField(
        max_length=20,
        choices=[
            ('free_trial', 'Free Trial (30 days)'),
            ('basic', 'Basic ($29/month)'),
            ('premium', 'Premium ($79/month)'),
            ('enterprise', 'Enterprise ($149/month)'),
        ],
        default='free_trial'
    )
    subscription_active = models.BooleanField(
        default=False,
        help_text="Has active paid subscription"
    )
    subscription_started_at = models.DateTimeField(null=True, blank=True)
    subscription_expires_at = models.DateTimeField(null=True, blank=True)

    # Profile visibility
    profile_visibility = models.CharField(
        max_length=20,
        choices=[
            ('public', 'Public - Listed in marketplace'),
            ('unlisted', 'Unlisted - Accessible via direct link only'),
            ('private', 'Private - Not accessible'),
        ],
        default='public'
    )
    is_featured = models.BooleanField(
        default=False,
        help_text="Featured trainers appear at top of search results"
    )

    # Auto-calculated marketplace stats
    total_reviews = models.IntegerField(default=0, editable=False)
    average_rating = models.DecimalField(
        max_digits=3,
        decimal_places=2,
        default=0.00,
        editable=False
    )
    total_sessions_completed = models.IntegerField(default=0, editable=False)
    response_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0.00,
        editable=False,
        help_text="% of messages responded to within 24 hours"
    )

    # === CLIENT-SPECIFIC FIELDS ===
    # Fitness Info
    fitness_goals = models.JSONField(
        default=list,
        blank=True,
        help_text='["Build Muscle", "Lose Weight", "Increase Endurance"]'
    )
    fitness_level = models.CharField(
        max_length=20,
        choices=[
            ('beginner', 'Beginner'),
            ('intermediate', 'Intermediate'),
            ('advanced', 'Advanced'),
        ],
        blank=True,
        null=True
    )
    injuries_limitations = models.TextField(
        blank=True,
        help_text="Any injuries, medical conditions, or physical limitations"
    )

    # Preferences (for trainer matching)
    preferred_trainer_gender = models.CharField(
        max_length=20,
        choices=[
            ('no_preference', 'No Preference'),
            ('male', 'Male'),
            ('female', 'Female'),
            ('non_binary', 'Non-Binary'),
        ],
        default='no_preference',
        blank=True
    )

    # === PRIVACY SETTINGS (ALL USERS) ===
    allow_trainer_requests = models.BooleanField(
        default=True,
        help_text="Allow trainers to send connection requests (clients only)"
    )
    show_workout_stats_publicly = models.BooleanField(
        default=False,
        help_text="Show workout stats on public profile"
    )

    # === METADATA ===
    date_created = models.DateTimeField(auto_now_add=True)
    date_updated = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-date_created']
        indexes = [
            models.Index(fields=['city', 'state']),
            models.Index(fields=['latitude', 'longitude']),
            models.Index(fields=['is_accepting_clients', 'subscription_active']),
        ]

    def __str__(self):
        return f"{self.user.full_name or self.user.username}'s Profile"

    # === VALIDATION ===
    def clean(self):
        """Validate role-specific requirements"""
        if self.user.role == 'trainer':
            # Trainers need location for marketplace
            if not self.city or not self.state:
                raise ValidationError(
                    "Trainers must provide city and state for marketplace listing."
                )

            # Trainers should have at least basic info
            if not self.bio:
                raise ValidationError("Trainers must provide a bio.")

            # If accepting clients, need pricing
            if self.is_accepting_clients and not self.hourly_rate:
                raise ValidationError(
                    "Trainers accepting clients must set an hourly rate."
                )

    # === COMPUTED PROPERTIES ===
    @property
    def age(self):
        """Calculate age from date of birth"""
        if not self.date_of_birth:
            return None
        today = timezone.now().date()
        return today.year - self.date_of_birth.year - (
                (today.month, today.day) < (self.date_of_birth.month, self.date_of_birth.day)
        )

    @property
    def display_location(self):
        """Human-readable location string"""
        if self.city and self.state:
            return f"{self.city}, {self.state}"
        elif self.city:
            return self.city
        elif self.state:
            return self.state
        return "Location not specified"

    @property
    def current_client_count(self):
        """Count active clients (trainers only)"""
        if self.user.role != 'trainer':
            return 0
        try:
            from connections.models import TrainerClientConnection
            return TrainerClientConnection.objects.filter(
                trainer=self.user,
                status='active'
            ).count()
        except:
            return 0

    @property
    def can_accept_clients(self):
        """Check if trainer can accept more clients"""
        if self.user.role != 'trainer':
            return False
        if not self.is_accepting_clients:
            return False
        if not self.subscription_active:
            return False  # Must have active subscription
        if self.max_clients and self.current_client_count >= self.max_clients:
            return False
        return True

    @property
    def is_profile_complete(self):
        """Check if profile has minimum required info"""
        if self.user.role == 'trainer':
            return all([
                self.bio,
                self.city,
                self.state,
                self.specializations,
                self.hourly_rate,
            ])
        else:  # client
            return all([
                self.city,
                self.fitness_level,
            ])

    @property
    def subscription_days_remaining(self):
        """Days until subscription expires"""
        if not self.subscription_expires_at:
            return 0
        delta = self.subscription_expires_at - timezone.now()
        return max(0, delta.days)


# === EXISTING MODELS (unchanged) ===

class EmailVerificationToken(models.Model):
    """One-time token for email verification."""
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    token = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def is_expired(self):
        """Token expires after 24 hours"""
        return timezone.now() > self.created_at + timezone.timedelta(hours=24)

    def __str__(self):
        return f"Token for {self.user.email}"


class PasswordResetToken(models.Model):
    """One-time token for password reset."""
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    token = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def is_expired(self):
        """Token expires after 30 minutes"""
        return timezone.now() > self.created_at + timezone.timedelta(minutes=30)

    def __str__(self):
        return f"Reset token for {self.user.email}"


# === SIGNAL HANDLERS ===

def create_user_profile(sender, instance, created, **kwargs):
    """Automatically create profile when user is created"""
    if created:
        Profile.objects.create(user=instance)


def send_email_verification_on_create(sender, instance, created, **kwargs):
    """Send verification email when user registers."""
    if created and not instance.is_verified:
        token, _ = EmailVerificationToken.objects.get_or_create(user=instance)

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
# post_save.connect(send_email_verification_on_create, sender=User)