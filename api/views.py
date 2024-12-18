from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from .models import User
import uuid
from .authentication import APIKeyAuthentication
import logging
from core.agents.base_agent import AIAgent
from core.agents.risk_agent import RiskAgent
from django.conf import settings
import os
from asgiref.sync import async_to_sync
from functools import wraps
import asyncio
from core.nli import NLIRouter

logger = logging.getLogger(__name__)

# Initialize the router
nli_router = NLIRouter()

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
        
        # Check if user already has an API key
        if user.api_key:
            return Response({
                'error': 'API key already exists for this user. Use get-api-key endpoint to retrieve it.',
                'username': user.username
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Generate new API key only if one doesn't exist
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
@permission_classes([AllowAny])
def get_api_key(request):
    """Get the existing API key for a user"""
    try:
        username = request.data.get('username')
        if not username:
            return Response({
                'error': 'Username is required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            user = User.objects.get(username=username)
            
            # Check if user has an API key
            if not user.api_key:
                # Generate one if they don't have it
                user.api_key = uuid.uuid4()
                user.save()
            
            return Response({
                'api_key': user.api_key,
                'username': user.username
            }, status=status.HTTP_200_OK)
            
        except User.DoesNotExist:
            return Response({
                'error': 'User not found. Please register first.'
            }, status=status.HTTP_404_NOT_FOUND)
            
    except Exception as e:
        logger.exception("Error in get_api_key:")
        return Response({
            'error': 'Internal server error',
            'detail': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

risk_agent = RiskAgent()  # Add risk agent initialization

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
        context = request.data.get('context', {})
        
        # Validate and process context
        if isinstance(context, dict) and 'history' in context:
            conversation_history = context['history']
            if not isinstance(conversation_history, list):
                return Response({'error': 'Context history must be a list'}, status=400)
            
            # Validate each history item
            for item in conversation_history:
                if not isinstance(item, dict) or 'role' not in item or 'content' not in item:
                    return Response({'error': 'Invalid history item format'}, status=400)
        else:
            conversation_history = []

        logger.info(f"Processing message with history length: {len(conversation_history)}")
        
        if not message:
            return Response({'error': 'Message is required'}, status=400)
        
        # Pass the processed context to the router
        response = await nli_router.route_message(message, {'history': conversation_history})
        return Response(response)
        
    except Exception as e:
        logger.exception("Error in agent view:")
        return Response({
            'error': str(e)
        }, status=500)
    
@async_api_view
async def risk_analysis(request):
    try:
        message = request.data.get('message')
        context = request.data.get('context', {})
        
        if not message:
            return Response({'error': 'Message is required'}, status=400)

        response = await risk_agent.process_message(message, context)
        return Response(response)
        
    except Exception as e:
        logger.exception("Error in risk analysis view:")
        return Response({
            'error': str(e)
        }, status=500)