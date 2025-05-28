# users/pipeline.py
from .models import UserProfile, User
from django.utils.timezone import now

def save_profile(backend, user, response, *args, **kwargs):
    if backend.name == 'google-oauth2':
        email = response.get('email')
        name = response.get('name')
        picture = response.get('picture')

        # Set username ONLY if it's the user's first login
        if not user.username:
            user.username = ""
            user.save()

        # Save user_id to session for Django-side usage
        kwargs['request'].session['user_id'] = user.id

        # Save to custom UserProfile only if not created yet
        profile, created = UserProfile.objects.get_or_create(
            user=user,
            defaults={
                'full_name': name,
                'profile_picture': picture
            }
        )
