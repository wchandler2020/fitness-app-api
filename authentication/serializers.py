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
            return user
        except ValidationError as e:
            raise serializers.ValidationError(e.messages)


class UserSerializer(serializers.ModelSerializer):
    """
    Basic user serializer for profile/auth responses.
    """
    class Meta:
        model = User
        fields = (
            'id', 
            'email', 
            'full_name', 
            'username', 
            'phone_number',
            'role',
            'is_verified',
            'date_joined'
        )
        read_only_fields = ('id', 'username', 'role', 'is_verified', 'date_joined')


class ProfileSerializer(serializers.ModelSerializer):
    """
    Extended profile serializer with nested user data.
    """
    user = UserSerializer(read_only=True)
    avatar = serializers.SerializerMethodField()

    class Meta:
        model = Profile
        fields = '__all__'

    def get_avatar(self, obj):
        """Return full URL for avatar image"""
        if obj.avatar:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.avatar.url)
            return obj.avatar.url
        return None


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