# users/serializers.py
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from .models import User, Profile


class MyTokenObtainPairSerializer(TokenObtainPairSerializer):
    """
    Custom JWT serializer - adds user info to token payload.
    Simpler than ProMed (no MFA yet for MVP).
    """
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token['full_name'] = user.full_name
        token['email'] = user.email
        token['username'] = user.username
        token['role'] = user.role
        return token

    def validate(self, attrs):
        """
        Validate credentials and check email verification.
        Removed MFA/approval checks from ProMed for MVP simplicity.
        """
        data = super().validate(attrs)
        user = authenticate(
            request=self.context.get('request'),
            email=attrs.get('email'),
            password=attrs.get('password')
        )
        
        if user and not user.is_verified:
            raise serializers.ValidationError({
                "detail": "Email not verified. Please check your inbox for a verification link."
            })
        
        return data


class RegisterSerializer(serializers.ModelSerializer):
    """
    User registration serializer.
    Much simpler than ProMed - only essential fields for fitness app.
    """
    password = serializers.CharField(
        write_only=True, 
        required=True, 
        validators=[validate_password]
    )
    password2 = serializers.CharField(write_only=True, required=True)
    role = serializers.ChoiceField(
        choices=['client', 'trainer'], 
        default='client',
        help_text="Select 'client' if you're looking for training, 'trainer' if you're coaching others."
    )

    class Meta:
        model = User
        fields = (
            'full_name', 
            'email', 
            'phone_number', 
            'password', 
            'password2',
            'role'
        )
        extra_kwargs = {
            'email': {'required': True},
            'full_name': {'required': True},
            'phone_number': {'required': False}
        }

    def validate(self, attrs):
        """Validate passwords match"""
        if attrs['password'] != attrs['password2']:
            raise serializers.ValidationError({
                "password": "Password fields didn't match."
            })
        return attrs

    def create(self, validated_data):
        """Create user and trigger email verification"""
        validated_data.pop('password2')
        
        try:
            user = User.objects.create_user(
                username=validated_data['email'],
                email=validated_data['email'],
                full_name=validated_data['full_name'],
                phone_number=validated_data.get('phone_number', ''),
                password=validated_data['password'],
                role=validated_data.get('role', 'client'),
            )
            user.is_verified = True
            user.save()
            return user
        except ValidationError as e:
            raise serializers.ValidationError(e.messages)


class ProfileSerializer(serializers.ModelSerializer):
    """
    Universal profile serializer.
    Dynamically includes/excludes fields based on user role.
    """
    age = serializers.IntegerField(read_only=True)
    display_location = serializers.CharField(read_only=True)
    current_client_count = serializers.IntegerField(read_only=True)
    can_accept_clients = serializers.BooleanField(read_only=True)
    is_profile_complete = serializers.BooleanField(read_only=True)
    subscription_days_remaining = serializers.IntegerField(read_only=True)

    class Meta:
        model = Profile
        fields = '__all__'
        read_only_fields = [
            'total_reviews', 'average_rating', 'total_sessions_completed',
            'response_rate', 'subscription_active', 'is_featured'
        ]

    def to_representation(self, instance):
        """
        Customize output based on user role and viewer.
        """
        data = super().to_representation(instance)
        user = instance.user
        request = self.context.get('request')

        # If viewer is not the profile owner, hide private fields
        if request and request.user != user:
            # Remove sensitive info for non-owners
            data.pop('contact_phone', None)
            data.pop('contact_email', None)
            data.pop('subscription_tier', None)
            data.pop('subscription_expires_at', None)

            # For clients viewing trainer profiles, show public info only
            if user.role == 'trainer':
                # Keep these visible
                pass

            # For trainers viewing client profiles, respect privacy
            if user.role == 'client':
                if not instance.show_workout_stats_publicly:
                    data.pop('fitness_goals', None)
                    data.pop('injuries_limitations', None)

        # If user is a client, remove trainer-only fields
        if user.role == 'client':
            trainer_only_fields = [
                'specializations', 'certifications', 'years_experience',
                'offers_in_person', 'offers_virtual', 'offers_home_visits',
                'offers_gym_sessions', 'preferred_gym_name', 'service_radius',
                'hourly_rate', 'package_pricing', 'is_accepting_clients',
                'max_clients', 'subscription_tier', 'subscription_active',
                'total_reviews', 'average_rating', 'response_rate'
            ]
            for field in trainer_only_fields:
                data.pop(field, None)

        return data


class UserSerializer(serializers.ModelSerializer):
    """User serializer with embedded profile"""
    profile = ProfileSerializer(read_only=True)

    class Meta:
        model = User
        fields = [
            'id', 'email', 'full_name', 'phone_number',
            'role', 'is_verified', 'date_joined', 'profile'
        ]
        read_only_fields = ['id', 'date_joined', 'is_verified']

class ProfileUpdateSerializer(serializers.ModelSerializer):
    """
    Separate serializer for profile updates.
    Validates role-specific requirements.
    """

    class Meta:
        model = Profile
        exclude = [
            'user', 'total_reviews', 'average_rating',
            'total_sessions_completed', 'response_rate',
            'is_featured', 'subscription_active'
        ]

    def validate(self, data):
        """Validate based on user role"""
        user = self.instance.user if self.instance else self.context['request'].user

        if user.role == 'trainer':
            # Trainers must have location
            if not data.get('city') and not self.instance.city:
                raise serializers.ValidationError({
                    'city': 'Trainers must provide a city.'
                })
            if not data.get('state') and not self.instance.state:
                raise serializers.ValidationError({
                    'state': 'Trainers must provide a state.'
                })

            # Trainers accepting clients need pricing
            if data.get('is_accepting_clients', self.instance.is_accepting_clients):
                if not data.get('hourly_rate') and not self.instance.hourly_rate:
                    raise serializers.ValidationError({
                        'hourly_rate': 'Set an hourly rate to accept clients.'
                    })

        return data


class RequestPasswordResetSerializer(serializers.Serializer):
    """
    Request password reset link via email.
    """
    email = serializers.EmailField(required=True)


class ResetPasswordSerializer(serializers.Serializer):
    """
    Reset password with token.
    """
    password = serializers.CharField(write_only=True, validators=[validate_password])
    confirm_password = serializers.CharField(write_only=True)

    def validate(self, data):
        """Validate passwords match"""
        if data['password'] != data['confirm_password']:
            raise serializers.ValidationError("Passwords do not match.")
        return data