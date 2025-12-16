# workouts/serializers.py
from rest_framework import serializers
from .models import Exercise, WorkoutLog, ExerciseLog, PersonalRecord
from django.utils import timezone


class ExerciseSerializer(serializers.ModelSerializer):
    """
    Exercise serializer for the master exercise library.
    """
    is_custom = serializers.SerializerMethodField()

    class Meta:
        model = Exercise
        fields = [
            'id', 'name', 'description', 'video_url',
            'muscle_groups', 'equipment', 'difficulty',
            'is_official', 'is_custom', 'created_at'
        ]
        read_only_fields = ['id', 'created_at', 'is_official']

    def get_is_custom(self, obj):
        """Check if this is a user's custom exercise"""
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return obj.created_by == request.user
        return False


class ExerciseLogSerializer(serializers.ModelSerializer):
    """
    Serializer for individual exercises within a workout.
    """
    exercise_details = ExerciseSerializer(source='exercise', read_only=True)
    completed_sets = serializers.IntegerField(source='get_completed_sets_count', read_only=True)
    total_volume = serializers.DecimalField(
        source='calculate_volume',
        max_digits=8,
        decimal_places=2,
        read_only=True
    )
    max_weight = serializers.DecimalField(
        source='get_max_weight',
        max_digits=6,
        decimal_places=2,
        read_only=True
    )

    class Meta:
        model = ExerciseLog
        fields = [
            'id', 'exercise', 'exercise_details', 'order',
            'sets_data', 'target_sets', 'target_reps', 'target_weight',
            'rest_seconds', 'notes',
            'completed_sets', 'total_volume', 'max_weight',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def validate_sets_data(self, value):
        """
        Validate sets_data structure.
        Expected format: [{"set": 1, "reps": 10, "weight": 135, "rpe": 7, "completed": true}, ...]
        """
        if not isinstance(value, list):
            raise serializers.ValidationError("sets_data must be a list")

        for i, set_obj in enumerate(value):
            if not isinstance(set_obj, dict):
                raise serializers.ValidationError(f"Set {i + 1} must be an object")

            # Required fields
            if 'set' not in set_obj:
                raise serializers.ValidationError(f"Set {i + 1} missing 'set' number")

            # Validate types
            if 'reps' in set_obj and not isinstance(set_obj['reps'], (int, float)):
                raise serializers.ValidationError(f"Set {i + 1} 'reps' must be a number")

            if 'weight' in set_obj and not isinstance(set_obj['weight'], (int, float)):
                raise serializers.ValidationError(f"Set {i + 1} 'weight' must be a number")

        return value


class WorkoutLogListSerializer(serializers.ModelSerializer):
    """
    Lightweight serializer for workout list views.
    """
    exercise_count = serializers.IntegerField(source='exercise_logs.count', read_only=True)
    total_volume = serializers.SerializerMethodField()

    class Meta:
        model = WorkoutLog
        fields = [
            'id', 'name', 'workout_date', 'duration_minutes',
            'exercise_count', 'total_volume',
            'energy_rating', 'difficulty_rating',
            'is_favorite', 'is_template', 'template_name',
            'created_at'
        ]
        read_only_fields = ['id', 'created_at']

    def get_total_volume(self, obj):
        """Calculate total volume for this workout"""
        return obj.calculate_total_volume()


class WorkoutLogDetailSerializer(serializers.ModelSerializer):
    """
    Full workout serializer with nested exercises.
    """
    exercise_logs = ExerciseLogSerializer(many=True, read_only=True)
    total_volume = serializers.SerializerMethodField()
    prs_achieved = serializers.SerializerMethodField()

    class Meta:
        model = WorkoutLog
        fields = [
            'id', 'name', 'notes', 'workout_date',
            'start_time', 'end_time', 'duration_minutes',
            'energy_rating', 'difficulty_rating',
            'is_favorite', 'is_template', 'template_name',
            'is_shared_with_trainer',
            'exercise_logs', 'total_volume', 'prs_achieved',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_total_volume(self, obj):
        return obj.calculate_total_volume()

    def get_prs_achieved(self, obj):
        """Return any PRs achieved in this workout"""
        prs = obj.prs_achieved.all()
        return PersonalRecordSerializer(prs, many=True).data


class WorkoutLogCreateSerializer(serializers.ModelSerializer):
    """
    Create/Update workout with nested exercises.
    """
    exercise_logs = ExerciseLogSerializer(many=True)

    class Meta:
        model = WorkoutLog
        fields = [
            'name', 'notes', 'workout_date',
            'start_time', 'end_time', 'duration_minutes',
            'energy_rating', 'difficulty_rating',
            'is_favorite', 'is_template', 'template_name',
            'exercise_logs'
        ]

    def create(self, validated_data):
        """Create workout with nested exercises"""
        exercise_logs_data = validated_data.pop('exercise_logs')
        user = self.context['request'].user

        # Create workout log
        workout_log = WorkoutLog.objects.create(user=user, **validated_data)

        # Create exercise logs
        for exercise_data in exercise_logs_data:
            ExerciseLog.objects.create(workout_log=workout_log, **exercise_data)

        # Check for PRs (will implement in views)

        return workout_log

    def update(self, instance, validated_data):
        """Update workout and its exercises"""
        exercise_logs_data = validated_data.pop('exercise_logs', None)

        # Update workout fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        # Update exercises if provided
        if exercise_logs_data is not None:
            # Delete old exercise logs
            instance.exercise_logs.all().delete()

            # Create new ones
            for exercise_data in exercise_logs_data:
                ExerciseLog.objects.create(workout_log=instance, **exercise_data)

        return instance


class CopyWorkoutSerializer(serializers.Serializer):
    """
    Serializer for copying a previous workout to a new date.
    """
    source_workout_id = serializers.IntegerField()
    new_workout_date = serializers.DateField(default=timezone.now)
    copy_as_template = serializers.BooleanField(default=False)
    new_name = serializers.CharField(required=False, allow_blank=True)

    def validate_source_workout_id(self, value):
        """Ensure workout exists and belongs to user"""
        user = self.context['request'].user
        try:
            workout = WorkoutLog.objects.get(id=value, user=user)
        except WorkoutLog.DoesNotExist:
            raise serializers.ValidationError("Workout not found or doesn't belong to you")
        return value


class PersonalRecordSerializer(serializers.ModelSerializer):
    """
    Personal record serializer.
    """
    exercise_name = serializers.CharField(source='exercise.name', read_only=True)
    user_name = serializers.CharField(source='user.full_name', read_only=True)

    class Meta:
        model = PersonalRecord
        fields = [
            'id', 'exercise', 'exercise_name', 'user_name',
            'pr_type', 'weight', 'reps', 'volume',
            'date_achieved', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']


class WorkoutStatsSerializer(serializers.Serializer):
    """
    Serializer for workout statistics/metrics.
    """
    total_workouts = serializers.IntegerField()
    total_volume = serializers.DecimalField(max_digits=10, decimal_places=2)
    workouts_this_week = serializers.IntegerField()
    workouts_this_month = serializers.IntegerField()
    current_streak_days = serializers.IntegerField()
    favorite_exercises = serializers.ListField(child=serializers.DictField())
    recent_prs = PersonalRecordSerializer(many=True)