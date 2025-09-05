from django.db import models
from django.utils import timezone
# Create your models here.
class AdminTaskLog(models.Model):
    TASK_CHOICES = [
        ("aggregation", "Aggregation & Pruning"),
        ("similarity", "Recalculate Similarity"),
        ("trending_cache", "Refresh Trending Cache"),
    ]
    task_name = models.CharField(max_length=50, choices=TASK_CHOICES)
    run_at = models.DateTimeField(default=timezone.now)
    status = models.CharField(max_length=20, default="success")  
    details = models.TextField(blank=True)