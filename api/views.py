from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from .models import User
import uuid
from .authentication import APIKeyAuthentication
import logging
from .agents.base_agent.base_agent import AIAgent
from django.conf import settings
import os
from asgiref.sync import async_to_sync
from functools import wraps
import asyncio

logger = logging.getLogger(__name__)

@api_view(['POST'])
@permission_classes([AllowAny])
def login_or_create(request):
    try:
        # Log the incoming request data
        logger.error(f"Request data: {request.data}")
        
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
    
    except Exception as e:
        # Log the full error with traceback
        logger.exception("Error in login_or_create:")
        return Response({
            'error': 'Internal server error',
            'detail': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
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

ai_agent = AIAgent()

def async_api_view(view):
    """
    Decorator for async API views
    """
    @api_view(['POST'])
    @authentication_classes([APIKeyAuthentication])
    @wraps(view)
    def wrapped_view(request, *args, **kwargs):
        # Run the async view in the current event loop
        async def run():
            return await view(request, *args, **kwargs)
        
        return async_to_sync(run)()
    
    return wrapped_view

@async_api_view
async def agent(request):
    try:
        message = request.data.get('message')
        if not message:
            return Response({'error': 'Message is required'}, status=400)

        # Process the message
        response = await ai_agent.process_message(message)
        
        # Return a proper Response object
        return Response({
            'response': response
        })
    except Exception as e:
        logger.exception("Error in agent view:")
        return Response({
            'error': str(e)
        }, status=500)