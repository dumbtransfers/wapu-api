from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from .models import User
import uuid
from .authentication import APIKeyAuthentication
@api_view(['POST'])
@permission_classes([AllowAny])
def login_or_create(request):
    username = request.data.get('username')
    if not username:
        return Response({
            'error': 'Username is required'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    # Get or create user
    user, created = User.objects.get_or_create(username=username)
    
    return Response({
        'message': 'User created successfully' if created else 'Login successful',
        'username': user.username
    }, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)

@api_view(['POST'])
@permission_classes([AllowAny])
def generate_api_key(request):
    username = request.data.get('username')
    if not username:
        return Response({
            'error': 'Username is required'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        user = User.objects.get(username=username)
        user.api_key = uuid.uuid4()
        user.save()
        
        return Response({
            'api_key': user.api_key,
            'username': user.username
        }, status=status.HTTP_201_CREATED)
    except User.DoesNotExist:
        return Response({
            'error': 'User not found'
        }, status=status.HTTP_404_NOT_FOUND)

@api_view(['POST'])
@authentication_classes([APIKeyAuthentication])
def agent(request):
    return Response({
        'message': 'Agent endpoint reached successfully',
        'username': request.user.username
    })
