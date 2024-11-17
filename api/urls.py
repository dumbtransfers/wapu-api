from django.urls import path
from . import views

urlpatterns = [
    path('v0/login-or-create/', views.login_or_create, name='login-or-create'),
    path('v0/generate-api-key/', views.generate_api_key, name='generate-api-key'),
    path('v0/get-api-key/', views.get_api_key, name='get_api_key'),  # New endpoint
    path('v0/agent/', views.agent, name='agent'),
]