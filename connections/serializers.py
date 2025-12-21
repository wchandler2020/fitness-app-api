from rest_framework import serializers
from .models import TrainerClientConnection, ConnectionInvitation
from authentication.models import User, Profile


class TrainerPublicSerializer(serializers.ModelSerializer):
    """Public trainer info for search/browse"""
    profile = serializers.SerializerMethodField()
    current_client_count = serializers.IntegerField(
        source='profile.current_client_count',
        read_only=True
    )
    can_accept_clients = serializers.BooleanField(
        source='profile.can_accept_clients',
        read_only=True
    )

    class Meta:
        model = User
        fields = [
            'id', 'full_name', 'email',
            'profile', 'current_client_count', 'can_accept_clients'
        ]

    def get_profile(self, obj):
        return {
            'bio': obj.profile.bio,
            'specializations': obj.profile.specializations,
            'certifications': obj.profile.certifications,
            'years_experience': obj.profile.years_experience,
            'hourly_rate': obj.profile.hourly_rate,
            'avatar': obj.profile.avatar.url if obj.profile.avatar else None,
            'instagram_handle': obj.profile.instagram_handle,
        }


class ClientPublicSerializer(serializers.ModelSerializer):
    """Basic client info for trainers"""
    profile = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ['id', 'full_name', 'email', 'profile']

    def get_profile(self, obj):
        return {
            'avatar': obj.profile.avatar.url if obj.profile.avatar else None,
            'fitness_goals': obj.profile.fitness_goals,
            'fitness_level': obj.profile.fitness_level,
        }


class TrainerClientConnectionSerializer(serializers.ModelSerializer):
    trainer_details = TrainerPublicSerializer(source='trainer', read_only=True)
    client_details = ClientPublicSerializer(source='client', read_only=True)

    class Meta:
        model = TrainerClientConnection
        fields = [
            'id', 'trainer', 'client', 'status',
            'can_view_workouts', 'can_assign_workouts',
            'can_view_nutrition', 'can_view_progress_photos',
            'can_view_body_metrics', 'can_comment_workouts',
            'request_message', 'rejection_reason',
            'requested_at', 'connected_at', 'last_interaction',
            'trainer_details', 'client_details'
        ]
        read_only_fields = [
            'id', 'requested_at', 'connected_at', 'last_interaction'
        ]


class ConnectionRequestSerializer(serializers.Serializer):
    """For client to request connection with trainer"""
    trainer_id = serializers.IntegerField()
    request_message = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=500
    )

    def validate_trainer_id(self, value):
        try:
            trainer = User.objects.get(id=value, role='trainer')
            if not trainer.profile.can_accept_clients:
                raise serializers.ValidationError(
                    "This trainer is not accepting new clients."
                )
        except User.DoesNotExist:
            raise serializers.ValidationError("Trainer not found.")
        return value


class UpdatePermissionsSerializer(serializers.ModelSerializer):
    """Client updates what trainer can see"""

    class Meta:
        model = TrainerClientConnection
        fields = [
            'can_view_workouts', 'can_assign_workouts',
            'can_view_nutrition', 'can_view_progress_photos',
            'can_view_body_metrics', 'can_comment_workouts'
        ]