# connections/models.py

from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from auditlog.registry import auditlog


class TrainerClientConnection(models.Model):
    """
    Manages the relationship between trainers and clients.
    Includes granular permission controls for data sharing.
    """
    STATUS_CHOICES = [
        ('pending', 'Pending Request'),
        ('active', 'Active'),
        ('paused', 'Paused'),
        ('ended', 'Ended'),
        ('rejected', 'Rejected'),
    ]

    # Core relationship
    trainer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='client_connections',
        limit_choices_to={'role': 'trainer'}
    )
    client = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='trainer_connections',
        limit_choices_to={'role': 'client'}
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending'
    )

    # Permission flags - CLIENT controls these
    can_view_workouts = models.BooleanField(
        default=True,
        help_text="Trainer can view workout logs"
    )
    can_assign_workouts = models.BooleanField(
        default=True,
        help_text="Trainer can create and assign workouts"
    )
    can_view_nutrition = models.BooleanField(
        default=False,
        help_text="Trainer can view nutrition logs (if implemented)"
    )
    can_view_progress_photos = models.BooleanField(
        default=False,
        help_text="Trainer can view progress photos"
    )
    can_view_body_metrics = models.BooleanField(
        default=False,
        help_text="Trainer can view weight and measurements"
    )
    can_comment_workouts = models.BooleanField(
        default=True,
        help_text="Trainer can comment on workouts"
    )

    # Request details
    request_message = models.TextField(
        blank=True,
        help_text="Message from client when requesting connection"
    )
    rejection_reason = models.TextField(
        blank=True,
        help_text="Reason if trainer rejects"
    )

    # Metadata
    requested_at = models.DateTimeField(auto_now_add=True)
    connected_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    last_interaction = models.DateTimeField(auto_now=True)

    # Notes
    trainer_notes = models.TextField(
        blank=True,
        help_text="Private notes for trainer about this client"
    )

    class Meta:
        unique_together = ['trainer', 'client']
        ordering = ['-requested_at']
        indexes = [
            models.Index(fields=['trainer', 'status']),
            models.Index(fields=['client', 'status']),
        ]

    def __str__(self):
        return f"{self.trainer.full_name} → {self.client.full_name} ({self.status})"

    def clean(self):
        """Validate trainer and client roles"""
        if self.trainer.role != 'trainer':
            raise ValidationError("Trainer must have 'trainer' role")
        if self.client.role != 'client':
            raise ValidationError("Client must have 'client' role")
        if self.trainer == self.client:
            raise ValidationError("User cannot be their own trainer")

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class ConnectionInvitation(models.Model):
    """
    Trainers can send invitations to potential clients.
    Alternative to client-initiated requests.
    """
    trainer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='sent_invitations'
    )

    # Can invite by email even if they're not a user yet
    email = models.EmailField()
    full_name = models.CharField(max_length=255, blank=True)
    message = models.TextField(blank=True)

    # Status
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('accepted', 'Accepted'),
        ('declined', 'Declined'),
        ('expired', 'Expired'),
    ]
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending'
    )

    # If accepted, link to the user
    accepted_by_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='accepted_invitations'
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    def __str__(self):
        return f"Invitation from {self.trainer.full_name} to {self.email}"

    def is_expired(self):
        from django.utils import timezone
        return timezone.now() > self.expires_at


# Register for audit logging
auditlog.register(TrainerClientConnection, include_fields=[
    'status', 'can_view_workouts', 'can_view_nutrition',
    'can_view_progress_photos', 'can_view_body_metrics'
])
