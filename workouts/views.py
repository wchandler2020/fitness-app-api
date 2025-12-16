# workouts/views.py
from rest_framework import generics, status, filters
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.db.models import Count, Sum, Q, Max
from django.utils import timezone
from datetime import timedelta

from .models import Exercise, WorkoutLog, ExerciseLog, PersonalRecord
from .serializers import (
    ExerciseSerializer,
    WorkoutLogListSerializer,
    WorkoutLogDetailSerializer,
    WorkoutLogCreateSerializer,
    CopyWorkoutSerializer,
    PersonalRecordSerializer,
    WorkoutStatsSerializer,
)
from .ai_generator import generate_ai_workout


# ==================== EXERCISE LIBRARY ====================

class ExerciseListCreateView(generics.ListCreateAPIView):
    """
    List all exercises (official + user's custom) or create a new custom exercise.
    """
    serializer_class = ExerciseSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name', 'muscle_groups', 'equipment']
    ordering_fields = ['name', 'created_at']

    def get_queryset(self):
        """Return official exercises + user's custom exercises"""
        user = self.request.user
        return Exercise.objects.filter(
            Q(is_official=True) | Q(created_by=user)
        )

    def perform_create(self, serializer):
        """Save custom exercise with current user"""
        serializer.save(created_by=self.request.user, is_official=False)


class ExerciseDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    Get, update, or delete a specific exercise.
    Users can only modify/delete their own custom exercises.
    """
    serializer_class = ExerciseSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        return Exercise.objects.filter(
            Q(is_official=True) | Q(created_by=user)
        )

    def perform_update(self, serializer):
        """Only allow updates to custom exercises"""
        if self.get_object().is_official:
            raise PermissionError("Cannot modify official exercises")
        serializer.save()

    def perform_destroy(self, instance):
        """Only allow deletion of custom exercises"""
        if instance.is_official:
            raise PermissionError("Cannot delete official exercises")
        instance.delete()


# ==================== WORKOUT LOGS ====================

class WorkoutLogListView(generics.ListAPIView):
    """
    List all workouts for the authenticated user.
    Supports filtering by date range, favorites, templates.
    """
    serializer_class = WorkoutLogListSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ['workout_date', 'created_at']
    ordering = ['-workout_date']

    def get_queryset(self):
        user = self.request.user
        queryset = WorkoutLog.objects.filter(user=user)

        # Filter by date range
        start_date = self.request.query_params.get('start_date')
        end_date = self.request.query_params.get('end_date')
        if start_date:
            queryset = queryset.filter(workout_date__gte=start_date)
        if end_date:
            queryset = queryset.filter(workout_date__lte=end_date)

        # Filter by favorites
        is_favorite = self.request.query_params.get('is_favorite')
        if is_favorite == 'true':
            queryset = queryset.filter(is_favorite=True)

        # Filter by templates
        is_template = self.request.query_params.get('is_template')
        if is_template == 'true':
            queryset = queryset.filter(is_template=True)

        return queryset.prefetch_related('exercise_logs__exercise')


class WorkoutLogDetailView(generics.RetrieveAPIView):
    """
    Get detailed view of a single workout.
    """
    serializer_class = WorkoutLogDetailSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return WorkoutLog.objects.filter(user=self.request.user).prefetch_related(
            'exercise_logs__exercise',
            'prs_achieved__exercise'
        )


class WorkoutLogCreateView(generics.CreateAPIView):
    """
    Create a new workout log.
    """
    serializer_class = WorkoutLogCreateSerializer
    permission_classes = [IsAuthenticated]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        workout_log = serializer.save()

        # Check for PRs
        prs_achieved = self.check_for_prs(workout_log)

        # Return detailed response
        response_serializer = WorkoutLogDetailSerializer(workout_log)
        return Response({
            'workout': response_serializer.data,
            'prs_achieved': prs_achieved,
            'message': f'Workout logged successfully! {len(prs_achieved)} PR(s) achieved.' if prs_achieved else 'Workout logged successfully!'
        }, status=status.HTTP_201_CREATED)

    def check_for_prs(self, workout_log):
        """
        Check if any exercises in this workout set new PRs.
        Returns list of PR objects created.
        """
        prs_achieved = []
        user = workout_log.user

        for exercise_log in workout_log.exercise_logs.all():
            exercise = exercise_log.exercise
            max_weight = exercise_log.get_max_weight()
            total_volume = exercise_log.calculate_volume()

            # Check max weight PR
            if max_weight > 0:
                pr, created = PersonalRecord.objects.get_or_create(
                    user=user,
                    exercise=exercise,
                    pr_type='max_weight',
                    defaults={
                        'weight': max_weight,
                        'workout_log': workout_log,
                        'date_achieved': workout_log.workout_date
                    }
                )

                # Update if this is a new record
                if not created and max_weight > (pr.weight or 0):
                    pr.weight = max_weight
                    pr.workout_log = workout_log
                    pr.date_achieved = workout_log.workout_date
                    pr.save()
                    prs_achieved.append(pr)
                elif created:
                    prs_achieved.append(pr)

            # Check volume PR
            if total_volume > 0:
                pr, created = PersonalRecord.objects.get_or_create(
                    user=user,
                    exercise=exercise,
                    pr_type='max_volume',
                    defaults={
                        'volume': total_volume,
                        'workout_log': workout_log,
                        'date_achieved': workout_log.workout_date
                    }
                )

                if not created and total_volume > (pr.volume or 0):
                    pr.volume = total_volume
                    pr.workout_log = workout_log
                    pr.date_achieved = workout_log.workout_date
                    pr.save()
                    prs_achieved.append(pr)
                elif created:
                    prs_achieved.append(pr)

        return PersonalRecordSerializer(prs_achieved, many=True).data


class WorkoutLogUpdateView(generics.UpdateAPIView):
    """
    Update an existing workout log.
    """
    serializer_class = WorkoutLogCreateSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return WorkoutLog.objects.filter(user=self.request.user)


class WorkoutLogDeleteView(generics.DestroyAPIView):
    """
    Delete a workout log.
    """
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return WorkoutLog.objects.filter(user=self.request.user)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def copy_workout(request):
    """
    Copy a previous workout to create a new one.
    Useful for "repeat workout" feature.
    """
    serializer = CopyWorkoutSerializer(data=request.data, context={'request': request})
    serializer.is_valid(raise_exception=True)

    source_id = serializer.validated_data['source_workout_id']
    new_date = serializer.validated_data['new_workout_date']
    copy_as_template = serializer.validated_data['copy_as_template']
    new_name = serializer.validated_data.get('new_name')

    # Get source workout
    source_workout = WorkoutLog.objects.get(id=source_id, user=request.user)

    # Create new workout (copy)
    new_workout = WorkoutLog.objects.create(
        user=request.user,
        name=new_name or source_workout.name,
        notes=source_workout.notes,
        workout_date=new_date,
        is_template=copy_as_template,
        template_name=source_workout.template_name if copy_as_template else ''
    )

    # Copy all exercise logs
    for exercise_log in source_workout.exercise_logs.all():
        ExerciseLog.objects.create(
            workout_log=new_workout,
            exercise=exercise_log.exercise,
            order=exercise_log.order,
            sets_data=exercise_log.sets_data,  # Copy the entire sets structure
            target_sets=exercise_log.target_sets,
            target_reps=exercise_log.target_reps,
            target_weight=exercise_log.target_weight,
            rest_seconds=exercise_log.rest_seconds,
            notes=exercise_log.notes
        )

    response_serializer = WorkoutLogDetailSerializer(new_workout)
    return Response({
        'workout': response_serializer.data,
        'message': 'Workout copied successfully!'
    }, status=status.HTTP_201_CREATED)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def toggle_favorite(request, pk):
    """
    Toggle favorite status of a workout.
    """
    try:
        workout = WorkoutLog.objects.get(id=pk, user=request.user)
        workout.is_favorite = not workout.is_favorite
        workout.save()

        return Response({
            'is_favorite': workout.is_favorite,
            'message': 'Added to favorites!' if workout.is_favorite else 'Removed from favorites!'
        })
    except WorkoutLog.DoesNotExist:
        return Response(
            {'error': 'Workout not found'},
            status=status.HTTP_404_NOT_FOUND
        )


# ==================== STATISTICS & ANALYTICS ====================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def workout_stats(request):
    """
    Get comprehensive workout statistics for the user.
    """
    user = request.user

    # Total workouts
    total_workouts = WorkoutLog.objects.filter(user=user).count()

    # Total volume (all time)
    total_volume = sum(
        workout.calculate_total_volume()
        for workout in WorkoutLog.objects.filter(user=user)
    ) or 0

    # Workouts this week
    today = timezone.now().date()
    week_start = today - timedelta(days=today.weekday())
    workouts_this_week = WorkoutLog.objects.filter(
        user=user,
        workout_date__gte=week_start
    ).count()

    # Workouts this month
    month_start = today.replace(day=1)
    workouts_this_month = WorkoutLog.objects.filter(
        user=user,
        workout_date__gte=month_start
    ).count()

    # Current streak (consecutive days with workouts)
    current_streak = calculate_streak(user)

    # Favorite exercises (most logged)
    favorite_exercises = list(
        ExerciseLog.objects.filter(workout_log__user=user)
        .values('exercise__name')
        .annotate(count=Count('id'))
        .order_by('-count')[:5]
    )

    # Recent PRs
    recent_prs = PersonalRecord.objects.filter(user=user).order_by('-date_achieved')[:5]

    stats = {
        'total_workouts': total_workouts,
        'total_volume': round(total_volume, 2),
        'workouts_this_week': workouts_this_week,
        'workouts_this_month': workouts_this_month,
        'current_streak_days': current_streak,
        'favorite_exercises': favorite_exercises,
        'recent_prs': PersonalRecordSerializer(recent_prs, many=True).data
    }

    serializer = WorkoutStatsSerializer(stats)
    return Response(serializer.data)


def calculate_streak(user):
    """
    Calculate the current workout streak (consecutive days).
    """
    today = timezone.now().date()
    streak = 0
    current_date = today

    # Check each day going backwards
    while True:
        has_workout = WorkoutLog.objects.filter(
            user=user,
            workout_date=current_date
        ).exists()

        if has_workout:
            streak += 1
            current_date -= timedelta(days=1)
        else:
            break

        # Stop after checking 365 days
        if (today - current_date).days > 365:
            break

    return streak


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def personal_records(request):
    """
    Get all personal records for the user, optionally filtered by exercise.
    """
    user = request.user
    prs = PersonalRecord.objects.filter(user=user).select_related('exercise', 'workout_log')

    # Filter by exercise if provided
    exercise_id = request.query_params.get('exercise_id')
    if exercise_id:
        prs = prs.filter(exercise_id=exercise_id)

    serializer = PersonalRecordSerializer(prs, many=True)
    return Response(serializer.data)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def generate_ai_workout_view(request):
    """
    Generate an AI-powered workout for the authenticated user.
    Expects a JSON body with preferences, for example:
    {
        "fitness_level": "intermediate",
        "goals": "build muscle",
        "injuries": "none",
        "duration": 60,
        "focus_areas": ["upper body"],
        "equipment": ["barbell", "dumbbell"],
        "type": "strength"
    }
    """
    try:
        # You can pass the entire request.data as preferences, because
        # generate_ai_workout builds the user_profile internally.
        preferences = dict(request.data)

        workout_plan = generate_ai_workout(request.user, preferences)

        return Response(workout_plan, status=status.HTTP_200_OK)
    except Exception as e:
        return Response(
            {"detail": str(e)},
            status=status.HTTP_400_BAD_REQUEST
        )

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def save_ai_workout(request):
    """
    Save an AI-generated workout as a WorkoutLog + ExerciseLogs.

    Expected JSON body (same structure returned by generate_ai_workout_view):
    {
        "workout_name": "...",
        "description": "...",              # optional -> store in notes
        "estimated_duration": 60,          # optional
        "warm_up_notes": "...",           # optional
        "cool_down_notes": "...",         # optional
        "exercises": [
            {
                "exercise_id": 1,
                "order": 1,
                "target_sets": 3,
                "target_reps": "8-12",
                "rest_seconds": 90,
                "notes": "Form cues...",
                "starting_weight_suggestion": "..."
            }
        ]
    }
    """
    data = request.data
    user = request.user

    workout_name = data.get("workout_name") or "AI Generated Workout"
    description = data.get("description", "")
    exercises = data.get("exercises", [])

    if not exercises:
        return Response(
            {"detail": "No exercises provided."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Create WorkoutLog (adjust fields to match your model)
    workout_log = WorkoutLog.objects.create(
        user=user,
        name=workout_name,
        notes=description,
        workout_date=timezone.now().date(),
        is_template=False,
    )

    # Create ExerciseLogs
    for ex in exercises:
        exercise_id = ex.get("exercise_id")
        order = ex.get("order", 1)
        target_sets = ex.get("target_sets", 3)
        target_reps = ex.get("target_reps", "")
        rest_seconds = ex.get("rest_seconds", 90)
        notes = ex.get("notes", "")

        try:
            exercise = Exercise.objects.get(id=exercise_id)
        except Exercise.DoesNotExist:
            # You can choose to skip or fail hard; here we skip invalid ones
            continue

        # You already use a JSON field `sets_data` elsewhere; for AI workouts
        # it may start empty because the user hasn't logged actual sets yet.
        ExerciseLog.objects.create(
            workout_log=workout_log,
            exercise=exercise,
            order=order,
            sets_data=[],  # no performed sets yet
            target_sets=target_sets,
            target_reps=target_reps,
            target_weight=None,
            rest_seconds=rest_seconds,
            notes=notes,
        )

    response_serializer = WorkoutLogDetailSerializer(workout_log)
    return Response(
        {
            "workout": response_serializer.data,
            "message": "AI workout saved successfully.",
        },
        status=status.HTTP_201_CREATED,
    )