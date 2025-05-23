# users/pipeline.py
from .models import UserProfile, User
from django.utils.timezone import now

def save_profile(backend, user, response, *args, **kwargs):
    if backend.name == 'google-oauth2':
        email = response.get('email')
        name = response.get('name')
        picture = response.get('picture')

        user.username = ""
        user.save()
        kwargs['request'].session['user_id'] = user.id
        
        # Save to custom UserProfile
        profile, created = UserProfile.objects.get_or_create(
            user=user,
            defaults={
                'full_name': name,
                'profile_picture': picture
            }
        )
