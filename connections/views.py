# connections/views.py

from rest_framework import generics, status, filters
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.utils import timezone
from django.db.models import Q

from .models import TrainerClientConnection, ConnectionInvitation
from .serializers import (
    TrainerClientConnectionSerializer,
    ConnectionRequestSerializer,
    UpdatePermissionsSerializer,
    TrainerPublicSerializer,
    ClientPublicSerializer
)
from authentication.models import User


# ==================== TRAINER SEARCH & DISCOVERY ====================

class TrainerListView(generics.ListAPIView):
    """
    Browse/search available trainers.
    Public endpoint (no auth required for browsing).
    """
    serializer_class = TrainerPublicSerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = [
        'full_name', 'profile__specializations',
        'profile__certifications', 'profile__bio'
    ]
    ordering_fields = ['profile__years_experience', 'date_joined']

    def get_queryset(self):
        return User.objects.filter(
            role='trainer',
            is_verified=True,
            profile__is_accepting_clients=True
        ).select_related('profile')


class TrainerDetailView(generics.RetrieveAPIView):
    """Get detailed info about a specific trainer"""
    serializer_class = TrainerPublicSerializer
    queryset = User.objects.filter(role='trainer').select_related('profile')


# ==================== CONNECTION MANAGEMENT ====================

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def request_trainer_connection(request):
    """
    Client requests connection with a trainer.
    """
    if request.user.role != 'client':
        return Response(
            {'error': 'Only clients can request trainer connections.'},
            status=status.HTTP_403_FORBIDDEN
        )

    serializer = ConnectionRequestSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    trainer_id = serializer.validated_data['trainer_id']
    message = serializer.validated_data.get('request_message', '')

    trainer = User.objects.get(id=trainer_id)

    # Check if connection already exists
    existing = TrainerClientConnection.objects.filter(
        trainer=trainer,
        client=request.user
    ).first()

    if existing:
        if existing.status == 'pending':
            return Response(
                {'error': 'Request already pending.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        elif existing.status == 'active':
            return Response(
                {'error': 'You are already connected to this trainer.'},
                status=status.HTTP_400_BAD_REQUEST
            )

    # Create new connection request
    connection = TrainerClientConnection.objects.create(
        trainer=trainer,
        client=request.user,
        status='pending',
        request_message=message
    )

    # TODO: Send notification to trainer

    response_serializer = TrainerClientConnectionSerializer(connection)
    return Response(response_serializer.data, status=status.HTTP_201_CREATED)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def accept_connection_request(request, connection_id):
    """Trainer accepts a client's connection request"""
    if request.user.role != 'trainer':
        return Response(
            {'error': 'Only trainers can accept requests.'},
            status=status.HTTP_403_FORBIDDEN
        )

    try:
        connection = TrainerClientConnection.objects.get(
            id=connection_id,
            trainer=request.user,
            status='pending'
        )
    except TrainerClientConnection.DoesNotExist:
        return Response(
            {'error': 'Connection request not found.'},
            status=status.HTTP_404_NOT_FOUND
        )

    connection.status = 'active'
    connection.connected_at = timezone.now()
    connection.save()

    # TODO: Send notification to client

    serializer = TrainerClientConnectionSerializer(connection)
    return Response({
        'message': 'Connection accepted!',
        'connection': serializer.data
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def reject_connection_request(request, connection_id):
    """Trainer rejects a client's connection request"""
    if request.user.role != 'trainer':
        return Response(
            {'error': 'Only trainers can reject requests.'},
            status=status.HTTP_403_FORBIDDEN
        )

    try:
        connection = TrainerClientConnection.objects.get(
            id=connection_id,
            trainer=request.user,
            status='pending'
        )
    except TrainerClientConnection.DoesNotExist:
        return Response(
            {'error': 'Connection request not found.'},
            status=status.HTTP_404_NOT_FOUND
        )

    rejection_reason = request.data.get('reason', '')

    connection.status = 'rejected'
    connection.rejection_reason = rejection_reason
    connection.save()

    serializer = TrainerClientConnectionSerializer(connection)
    return Response({
        'message': 'Connection request rejected.',
        'connection': serializer.data
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def my_connections(request):
    """
    Get user's connections.
    - Clients see their trainers
    - Trainers see their clients
    """
    user = request.user

    if user.role == 'client':
        connections = TrainerClientConnection.objects.filter(
            client=user
        ).select_related('trainer__profile')
    else:  # trainer
        connections = TrainerClientConnection.objects.filter(
            trainer=user
        ).select_related('client__profile')

    # Filter by status if provided
    status_filter = request.query_params.get('status')
    if status_filter:
        connections = connections.filter(status=status_filter)

    serializer = TrainerClientConnectionSerializer(connections, many=True)
    return Response(serializer.data)


@api_view(['PUT'])
@permission_classes([IsAuthenticated])
def update_connection_permissions(request, connection_id):
    """
    Client updates what the trainer can see.
    Only the client can modify permissions.
    """
    if request.user.role != 'client':
        return Response(
            {'error': 'Only clients can update permissions.'},
            status=status.HTTP_403_FORBIDDEN
        )

    try:
        connection = TrainerClientConnection.objects.get(
            id=connection_id,
            client=request.user
        )
    except TrainerClientConnection.DoesNotExist:
        return Response(
            {'error': 'Connection not found.'},
            status=status.HTTP_404_NOT_FOUND
        )

    serializer = UpdatePermissionsSerializer(
        connection,
        data=request.data,
        partial=True
    )
    serializer.is_valid(raise_exception=True)
    serializer.save()

    response_serializer = TrainerClientConnectionSerializer(connection)
    return Response({
        'message': 'Permissions updated successfully.',
        'connection': response_serializer.data
    })


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def end_connection(request, connection_id):
    """
    End a trainer-client connection.
    Either party can end the connection.
    """
    try:
        connection = TrainerClientConnection.objects.get(
            Q(trainer=request.user) | Q(client=request.user),
            id=connection_id
        )
    except TrainerClientConnection.DoesNotExist:
        return Response(
            {'error': 'Connection not found.'},
            status=status.HTTP_404_NOT_FOUND
        )

    connection.status = 'ended'
    connection.ended_at = timezone.now()
    connection.save()

    return Response({
        'message': 'Connection ended successfully.'
    })
