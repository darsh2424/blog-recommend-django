from django.db import models

class User(models.Model):
    email = models.EmailField(unique=True)
    password = models.CharField(max_length=255)
    username = models.CharField(max_length=255, unique=True)

    def __str__(self):
        return self.username

class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    full_name = models.CharField(max_length=255, null=True, blank=True)
    gender = models.CharField(max_length=50, null=True, blank=True)
    birth_date = models.DateField(null=True, blank=True)
    location = models.CharField(max_length=100, blank=True, null=True)
    profile_picture = models.URLField(blank=True, null=True)
    followed_users = models.ManyToManyField("self", blank=True, symmetrical=False)
    category_preferences = models.JSONField(blank=True, null=True)
    saved_posts = models.ManyToManyField("blog.Post", blank=True)

    def __str__(self):
        return f"Profile of {self.user.username}"

class UserActivity(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="activities")
    post = models.ForeignKey("blog.Post", on_delete=models.CASCADE, related_name="activities")
    liked = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

class UserPostActivity(models.Model):
    ACTIONS = [('A', 'Added'), ('D', 'Deleted'), ('E', 'Edited')]
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="post_activities")
    post = models.ForeignKey("blog.Post", on_delete=models.CASCADE, related_name="post_activities")
    action_performed = models.CharField(max_length=255)
    action_status = models.CharField(max_length=1, choices=ACTIONS)
    created_at = models.DateTimeField(auto_now_add=True)
