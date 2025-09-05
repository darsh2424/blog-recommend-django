from django.utils import timesince,timezone
from django.db import models
from users.models import User

class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)

    class Meta:
        indexes = [
            models.Index(fields=['name']),
        ]

    def __str__(self):
        return self.name

class Post(models.Model):
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('published', 'Published'),
        ('suspended', 'Suspended'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="posts")
    title = models.CharField(max_length=255)
    content = models.TextField(blank=True, null=True)
    image_url = models.URLField(blank=True, null=True)
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name="posts")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    is_suspended = models.BooleanField(default=False)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='published')


    def __str__(self):
        return self.title

    @property
    def views_count(self):
        return self.interactions.filter(viewed=True).count()

    @property
    def like_count(self):
        return self.interactions.filter(liked=True).count()

    @property
    def comment_count(self):
        return self.comments.count()

class Comment(models.Model):
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name="comments")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="comments")
    text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Comment by {self.user.username} on {self.post.title}"
    
    @property
    def is_editable(self):
        return (timezone.now() - self.created_at).total_seconds() <= 86400  

    @property
    def replies_count(self):
        return self.replies.count()

class CommentReply(models.Model):
    comment = models.ForeignKey(Comment, on_delete=models.CASCADE, related_name="replies")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="comment_replies")
    text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    parent_comment = models.ForeignKey(Comment, on_delete=models.CASCADE, related_name="nested_replies", null=True, blank=True)

    def __str__(self):
        return f"Reply by {self.user.username} to comment {self.comment.id}"

    @property
    def is_editable(self):
        return (timezone.now() - self.created_at).total_seconds() <= 86400  

    @property
    def time_since(self):
        return timesince(self.created_at)


class PostReport(models.Model):
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name="reports")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="reports")
    reason = models.TextField()
    reported_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Report on {self.post.title} by {self.user.username}"

class PostStatusHistory(models.Model):
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name="status_history")
    old_status = models.CharField(max_length=20)
    new_status = models.CharField(max_length=20)
    changed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="post_status_changes")
    changed_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.post.title}: {self.old_status} → {self.new_status}"

class RecommendationLog(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    post = models.ForeignKey("Post", on_delete=models.CASCADE)
    tier = models.IntegerField(
        choices=[(3, "Engaged"), (2, "Fresh/Trending"), (1, "Exploration")],
        default=1
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["user", "tier", "created_at"]),
        ]
        ordering = ["-created_at"]


class RecommendationStats(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    tier = models.IntegerField(
        choices=[(3, "Engaged"), (2, "Fresh/Trending"), (1, "Exploration")],
        default=1
    )
    date = models.DateField()
    count = models.IntegerField(default=0)

    class Meta:
        unique_together = ("user", "tier", "date")
        indexes = [
            models.Index(fields=["date", "tier"]),
            models.Index(fields=["user", "date"]),
        ]

    def __str__(self):
        return f"{self.date} | {self.user} | Tier {self.tier} → {self.count}"
