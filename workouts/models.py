# workouts/models.py
from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator
from django.utils import timezone


class Exercise(models.Model):
    """
    Master exercise library - shared across all users.
    Can be admin-created or user-created.
    """
    DIFFICULTY_CHOICES = [
        ('beginner', 'Beginner'),
        ('intermediate', 'Intermediate'),
        ('advanced', 'Advanced'),
    ]

    EQUIPMENT_CHOICES = [
        ('barbell', 'Barbell'),
        ('dumbbell', 'Dumbbell'),
        ('machine', 'Machine'),
        ('bodyweight', 'Bodyweight'),
        ('cable', 'Cable'),
        ('kettlebell', 'Kettlebell'),
        ('medicine_ball', 'Medicine Ball'),
        ('pullup_bar', 'Pull-up Bar'),
        ('TRX', 'Suspension Trainer (TRX)'),
        ('resistance_band', 'Resistance Band'),
        ('treadmill', 'Treadmill'),
        ('rower', 'Rower'),
        ('plyo_box', 'Plyometric Box'),
        ('slam_ball', 'Slam Ball'),
        ('sled_prowler', 'Sled/Prowler'),
        ('stability_ball', 'Stability Ball'),
        ('foam_roller', 'Foam Roller'),
        ('other', 'Other'),
    ]

    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    video_url = models.URLField(blank=True, null=True, help_text="YouTube or demo video link")

    # Stored as JSON list: ["chest", "triceps", "shoulders"]
    muscle_groups = models.JSONField(
        default=list,
        help_text='List of muscle groups: ["chest", "triceps", "shoulders"]'
    )

    equipment = models.CharField(max_length=50, choices=EQUIPMENT_CHOICES, default='bodyweight')
    difficulty = models.CharField(max_length=20, choices=DIFFICULTY_CHOICES, default='beginner')

    # Track if this is a custom user exercise or official library exercise
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='custom_exercises'
    )
    is_official = models.BooleanField(default=False, help_text="Official library exercise")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        indexes = [
            models.Index(fields=['name']),
            models.Index(fields=['equipment']),
        ]

    def __str__(self):
        return self.name


class WorkoutLog(models.Model):
    """
    A single workout session logged by a client.
    This is the core entity - each workout log can contain multiple exercises.
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='workout_logs'
    )

    # Basic workout info
    name = models.CharField(
        max_length=200,
        help_text="e.g., 'Push Day', 'Leg Day', 'Full Body'"
    )
    notes = models.TextField(blank=True, help_text="Overall workout notes")

    # Date/Time tracking
    workout_date = models.DateField(default=timezone.now)
    start_time = models.TimeField(null=True, blank=True)
    end_time = models.TimeField(null=True, blank=True)
    duration_minutes = models.IntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1)],
        help_text="Total workout duration in minutes"
    )

    # Subjective metrics
    RATING_CHOICES = [(i, str(i)) for i in range(1, 6)]  # 1-5
    energy_rating = models.IntegerField(
        choices=RATING_CHOICES,
        null=True,
        blank=True,
        help_text="How energetic did you feel? (1-5)"
    )
    difficulty_rating = models.IntegerField(
        choices=RATING_CHOICES,
        null=True,
        blank=True,
        help_text="How hard was the workout? (1-5)"
    )

    # Favorites & Templates
    is_favorite = models.BooleanField(
        default=False,
        help_text="Mark as favorite for quick access"
    )
    is_template = models.BooleanField(
        default=False,
        help_text="Save as reusable template"
    )
    template_name = models.CharField(
        max_length=200,
        blank=True,
        help_text="Name for this template (if is_template=True)"
    )

    # Privacy control (for trainer sharing - Phase 3)
    is_shared_with_trainer = models.BooleanField(
        default=False,
        help_text="Client has shared this workout with their trainer"
    )

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-workout_date', '-created_at']
        indexes = [
            models.Index(fields=['user', '-workout_date']),
            models.Index(fields=['user', 'is_favorite']),
            models.Index(fields=['user', 'is_template']),
        ]

    def __str__(self):
        return f"{self.user.full_name} - {self.name} ({self.workout_date})"

    def calculate_total_volume(self):
        """Calculate total weight lifted (weight × reps × sets)"""
        total = 0
        for exercise_log in self.exercise_logs.all():
            total += exercise_log.calculate_volume()
        return total


class ExerciseLog(models.Model):
    """
    A single exercise within a workout log.
    Stores all sets for this exercise in a structured JSON format.
    """
    workout_log = models.ForeignKey(
        WorkoutLog,
        on_delete=models.CASCADE,
        related_name='exercise_logs'
    )
    exercise = models.ForeignKey(
        Exercise,
        on_delete=models.PROTECT,  # Don't delete exercise if it's been logged
        related_name='exercise_logs'
    )

    # Order within the workout
    order = models.PositiveIntegerField(default=0, help_text="Exercise order in workout")

    # Sets data stored as JSON:
    # [
    #   {"set": 1, "reps": 10, "weight": 135, "rpe": 7, "completed": true},
    #   {"set": 2, "reps": 8, "weight": 145, "rpe": 8, "completed": true},
    #   {"set": 3, "reps": 6, "weight": 155, "rpe": 9, "completed": false}
    # ]
    sets_data = models.JSONField(
        default=list,
        help_text="List of set objects with reps, weight, RPE, etc."
    )

    # Target prescription (optional - what the trainer assigned)
    target_sets = models.IntegerField(null=True, blank=True)
    target_reps = models.CharField(
        max_length=50,
        blank=True,
        help_text="e.g., '8-12', 'AMRAP', '10'"
    )
    target_weight = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True
    )

    # Notes for this specific exercise
    notes = models.TextField(blank=True)

    # Rest time between sets (seconds)
    rest_seconds = models.IntegerField(default=90, validators=[MinValueValidator(0)])

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['workout_log', 'order']
        indexes = [
            models.Index(fields=['workout_log', 'order']),
            models.Index(fields=['exercise']),
        ]

    def __str__(self):
        return f"{self.exercise.name} - {self.workout_log.name}"

    def calculate_volume(self):
        """Calculate total volume for this exercise (weight × reps × sets)"""
        total = 0
        for set_data in self.sets_data:
            if set_data.get('completed', False):
                reps = set_data.get('reps', 0)
                weight = set_data.get('weight', 0)
                total += reps * weight
        return total

    def get_completed_sets_count(self):
        """Count how many sets were actually completed"""
        return sum(1 for s in self.sets_data if s.get('completed', False))

    def get_max_weight(self):
        """Get the heaviest weight used in this exercise"""
        weights = [s.get('weight', 0) for s in self.sets_data if s.get('completed', False)]
        return max(weights) if weights else 0


class PersonalRecord(models.Model):
    """
    Track personal records for exercises.
    Auto-created when a new PR is detected.
    """
    PR_TYPE_CHOICES = [
        ('max_weight', 'Max Weight'),
        ('max_reps', 'Max Reps at Weight'),
        ('max_volume', 'Max Total Volume'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='personal_records'
    )
    exercise = models.ForeignKey(
        Exercise,
        on_delete=models.CASCADE,
        related_name='personal_records'
    )

    pr_type = models.CharField(max_length=20, choices=PR_TYPE_CHOICES)

    # PR values
    weight = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    reps = models.IntegerField(null=True, blank=True)
    volume = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)

    # Reference to the workout where this PR was achieved
    workout_log = models.ForeignKey(
        WorkoutLog,
        on_delete=models.SET_NULL,
        null=True,
        related_name='prs_achieved'
    )

    date_achieved = models.DateField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date_achieved']
        indexes = [
            models.Index(fields=['user', 'exercise', 'pr_type']),
        ]
        # Ensure one PR per user/exercise/type combination
        unique_together = ['user', 'exercise', 'pr_type']

    def __str__(self):
        return f"{self.user.full_name} - {self.exercise.name} {self.pr_type}: {self.weight}lbs x {self.reps}"
