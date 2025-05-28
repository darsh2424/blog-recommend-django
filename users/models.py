from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils import timezone

class CustomUserManager(BaseUserManager):
    def create_user(self, email, username=None, password=None, **extra_fields):
        if not email:
            raise ValueError('Email is required')
        email = self.normalize_email(email)
        user = self.model(email=email, username=username, **extra_fields)

        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()

        user.save(using=self._db)
        return user

    def create_superuser(self, email, username=None, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)

        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')

        return self.create_user(email, username, password, **extra_fields)

class User(AbstractBaseUser, PermissionsMixin):
    email = models.EmailField(unique=True)
    username = models.CharField(max_length=50, blank=True, null=True)
    created_at = models.DateTimeField(default=timezone.now)

    # Admin flags
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)

    objects = CustomUserManager()

    USERNAME_FIELD = 'email'  
    # REQUIRED_FIELDS = ['username']

    def __str__(self):
        return self.username or self.email

class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    full_name = models.CharField(max_length=255, null=True, blank=True)
    gender = models.CharField(max_length=50, null=True, blank=True)
    birth_date = models.DateField(null=True, blank=True)
    location = models.CharField(max_length=100, blank=True, null=True)
    profile_picture = models.URLField(blank=True, null=True)
    followed_users = models.ManyToManyField("self", blank=True, symmetrical=False)
    category_preferences = models.ManyToManyField("blog.Category", blank=True)
    saved_posts = models.ManyToManyField("blog.Post", blank=True)
    created_at = models.DateTimeField(auto_now_add=True, null=True)

    def __str__(self):
        return f"Profile of {self.user.username or self.user.email}"

class PostInteraction(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    post = models.ForeignKey("blog.Post", on_delete=models.CASCADE)
    liked = models.BooleanField(default=False)
    viewed = models.BooleanField(default=False)
    saved = models.BooleanField(default=False)
    timestamp = models.DateTimeField(auto_now=True)

class UserPostActivity(models.Model):
    ACTIONS = [('A', 'Added'), ('D', 'Deleted'), ('E', 'Edited')]
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="post_activities")
    post = models.ForeignKey("blog.Post", on_delete=models.CASCADE, related_name="post_activities")
    action_performed = models.CharField(max_length=255)
    action_status = models.CharField(max_length=1, choices=ACTIONS)
    created_at = models.DateTimeField(auto_now_add=True)
