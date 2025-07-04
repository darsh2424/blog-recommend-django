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
    
    def follow_user(self, user_profile):
        """Follow another user"""
        if user_profile not in self.followed_users.all():
            self.followed_users.add(user_profile)
            return True
        return False
    
    def unfollow_user(self, user_profile):
        """Unfollow another user"""
        if user_profile in self.followed_users.all():
            self.followed_users.remove(user_profile)
            return True
        return False
    
    def is_following(self, user_profile):
        """Check if current user is following another user"""
        return self.followed_users.filter(pk=user_profile.pk).exists()
    
    @property
    def followers_count(self):
        return UserProfile.objects.filter(followed_users=self).count()
    
    @property
    def followers(self):
        return UserProfile.objects.filter(followed_users=self)
    
    @property
    def following_count(self):
        return self.followed_users.count()
    
    @property
    def following_posts(self):
        """Get all posts from users I'm following"""
        from blog.models import Post  # Avoid circular imports
        return Post.objects.filter(
            user__profile__in=self.followed_users.all()
        ).order_by('-created_at')

class PostInteraction(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    post = models.ForeignKey("blog.Post", on_delete=models.CASCADE)
    liked = models.BooleanField(default=False)
    viewed = models.BooleanField(default=False)
    saved = models.BooleanField(default=False)
    timestamp = models.DateTimeField(auto_now=True)

class UserPostActivity(models.Model):
    ACTION_CHOICES = [
        ('A', 'Added'),
        ('D', 'Deleted'), 
        ('E', 'Edited'),
        ('U', 'Updated'),
    ]
    
    REASON_CHOICES = [
        ('typo', 'Fixed typos'),
        ('info', 'Added more information'),
        ('image', 'Updated image'),
        ('structure', 'Improved structure'),
        ('other', 'Other (please specify)'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="post_activities")
    post = models.ForeignKey("blog.Post", on_delete=models.CASCADE, related_name="activities")
    action = models.CharField(max_length=1, choices=ACTION_CHOICES, default='A')
    reason = models.CharField(max_length=20, choices=REASON_CHOICES, null=True)
    details = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = "User Post Activities"

