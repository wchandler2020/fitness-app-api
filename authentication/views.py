# users/views.py
from datetime import datetime
from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.mail import send_mail
from django.contrib.auth.password_validation import validate_password
from django.template.loader import render_to_string

from rest_framework import generics, status, permissions
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.views import TokenObtainPairView

from .models import User, Profile, EmailVerificationToken, PasswordResetToken
from .serializers import (
    MyTokenObtainPairSerializer,
    RegisterSerializer,
    UserSerializer,
    ProfileSerializer,
    RequestPasswordResetSerializer,
    ResetPasswordSerializer
)


class MyTokenObtainPairView(TokenObtainPairView):
    """
    Custom login endpoint with JWT tokens.
    Simplified from ProMed - no MFA or approval checks for MVP.
    """
    serializer_class = MyTokenObtainPairSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = serializer.user

        # Check email verification
        if not user.is_verified:
            return Response(
                {'detail': 'Your account is not verified. Please check your email.'},
                status=status.HTTP_401_UNAUTHORIZED
            )

        # Generate tokens
        refresh = serializer.validated_data['refresh']
        access = serializer.validated_data['access']
        
        user_data = UserSerializer(user).data

        return Response({
            'access': str(access),
            'refresh': str(refresh),
            'user': user_data,
            'detail': 'Login successful.'
        }, status=status.HTTP_200_OK)


class RegisterUser(generics.CreateAPIView):
    """
    User registration endpoint.
    Automatically sends verification email via signal.
    """
    queryset = User.objects.all()
    permission_classes = [AllowAny]
    serializer_class = RegisterSerializer

    def perform_create(self, serializer):
        """
        Create user and send verification email.
        Email sending is handled by the post_save signal in models.py,
        but we keep this override for potential future customization.
        """
        user = serializer.save()
        return user

    def create(self, request, *args, **kwargs):
        """Override to return custom success message"""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = self.perform_create(serializer)
        
        return Response({
            'message': 'Registration successful! Please check your email to verify your account.',
            'user': UserSerializer(user).data
        }, status=status.HTTP_201_CREATED)


class VerifyEmailView(generics.GenericAPIView):
    """
    Email verification endpoint.
    User clicks link from email with UUID token.
    """
    permission_classes = [AllowAny]

    def get(self, request, token):
        """Verify email with token from URL"""
        try:
            verification_token = EmailVerificationToken.objects.get(token=token)
            user = verification_token.user

            if user.is_verified:
                return Response(
                    {"message": "Email already verified."},
                    status=status.HTTP_200_OK
                )

            # Check if token expired
            if verification_token.is_expired():
                return Response(
                    {"error": "Verification link has expired. Please request a new one."},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Verify user
            user.is_verified = True
            user.save()
            verification_token.delete()

            # Send welcome email
            welcome_email_html = render_to_string(
                'users/welcome_email.html',
                {'user': user}
            )

            send_mail(
                subject='Welcome to Fitness Hub!',
                message='Thank you for verifying your email. Your account is now active!',
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
                html_message=welcome_email_html,
                fail_silently=True
            )

            return Response(
                {"message": "Email successfully verified! You can now log in."},
                status=status.HTTP_200_OK
            )

        except EmailVerificationToken.DoesNotExist:
            return Response(
                {"error": "Invalid or expired verification link."},
                status=status.HTTP_400_BAD_REQUEST
            )


class ResendVerificationEmail(generics.GenericAPIView):
    """
    Resend verification email if user didn't receive it.
    """
    permission_classes = [AllowAny]

    def post(self, request):
        """Resend verification email to provided email address"""
        email = request.data.get('email')
        
        if not email:
            return Response(
                {'error': 'Email is required.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            user = User.objects.get(email=email)
            
            if user.is_verified:
                return Response(
                    {'message': 'This email is already verified.'},
                    status=status.HTTP_200_OK
                )

            # Get or create new token
            token, created = EmailVerificationToken.objects.get_or_create(user=user)
            
            # If token exists and is old, delete and create new one
            if not created and token.is_expired():
                token.delete()
                token = EmailVerificationToken.objects.create(user=user)

            verification_link = f"{settings.FRONTEND_URL}/verify-email/{token.token}"

            email_html_message = render_to_string(
                'users/email_verification.html',
                {
                    'user': user,
                    'verification_link': verification_link
                }
            )

            send_mail(
                subject='Verify Your Email - Fitness Hub',
                message=f"Click the link to verify your email: {verification_link}",
                html_message=email_html_message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
                fail_silently=False
            )

            return Response(
                {'message': 'Verification email sent successfully.'},
                status=status.HTTP_200_OK
            )

        except User.DoesNotExist:
            # Don't reveal if email exists or not (security)
            return Response(
                {'message': 'If this email is registered, a verification link will be sent.'},
                status=status.HTTP_200_OK
            )


class ProfileView(generics.RetrieveUpdateAPIView):
    """
    Get or update authenticated user's profile.
    """
    serializer_class = ProfileSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        """Return current user's profile"""
        return self.request.user.profile


class RequestPasswordResetView(generics.GenericAPIView):
    """
    Request password reset link via email.
    """
    serializer_class = RequestPasswordResetSerializer
    permission_classes = [AllowAny]

    def post(self, request):
        """Send password reset email if user exists"""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data['email']

        try:
            user = User.objects.get(email=email)
            
            # Create reset token
            token = PasswordResetToken.objects.create(user=user)
            reset_link = f"{settings.FRONTEND_URL}/reset-password/{token.token}"

            html_message = render_to_string(
                'users/password_reset_email.html',
                {
                    'reset_link': reset_link,
                    'user': user,
                }
            )

            send_mail(
                subject='Password Reset Request - Fitness Hub',
                message=f'Click the link to reset your password: {reset_link}',
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
                html_message=html_message,
                fail_silently=False,
            )
        except User.DoesNotExist:
            pass  # Don't reveal if email exists

        # Always return same message (security best practice)
        return Response(
            {'message': 'If the email is registered, a reset link has been sent.'},
            status=status.HTTP_200_OK
        )


class ResetPasswordView(generics.GenericAPIView):
    """
    Reset password with token from email link.
    """
    serializer_class = ResetPasswordSerializer
    permission_classes = [AllowAny]

    def post(self, request, token):
        """Reset password using token"""
        try:
            reset_token = PasswordResetToken.objects.get(token=token)
        except PasswordResetToken.DoesNotExist:
            return Response(
                {'error': 'Invalid or expired token.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if reset_token.is_expired():
            reset_token.delete()
            return Response(
                {'error': 'Token has expired. Please request a new password reset link.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        password = serializer.validated_data['password']
        user = reset_token.user

        # Validate password strength
        try:
            validate_password(password, user=user)
        except DjangoValidationError as e:
            return Response(
                {'error': e.messages},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Set new password and delete token
        user.set_password(password)
        user.save()
        reset_token.delete()

        return Response(
            {'message': 'Password has been reset successfully. You can now log in.'},
            status=status.HTTP_200_OK
        )