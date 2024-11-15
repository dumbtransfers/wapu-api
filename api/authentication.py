from rest_framework import authentication
from rest_framework import exceptions
from .models import User

class APIKeyAuthentication(authentication.BaseAuthentication):
    def authenticate(self, request):
        api_key = request.headers.get('X-API-Key')
        if not api_key:
            return None

        try:
            user = User.objects.get(api_key=api_key)
            return (user, None)
        except User.DoesNotExist:
            raise exceptions.AuthenticationFailed('Invalid API key')
