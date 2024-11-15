from django.db import models
import uuid

class User(models.Model):
    username = models.CharField(max_length=100, unique=True)
    api_key = models.UUIDField(default=uuid.uuid4, editable=False, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.username