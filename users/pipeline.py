# users/pipeline.py
from .models import UserProfile
from django.utils.timezone import now

def save_profile(backend, user, response, *args, **kwargs):
    if backend.name == 'google-oauth2':
        email = response.get('email')
        name = response.get('name')
        picture = response.get('picture')

        # Only set username on first-time login (not every login)
        # if user.username is None or user.username.strip() == "":
        #     user.username = ""  
        #     user.save()

        # Save user_id in session for seamless Django use
        request = kwargs.get('request')
        if request:
            request.session['user_id'] = user.id

        # Get or create user profile; only insert defaults on creation
        profile_created = not UserProfile.objects.filter(user=user).exists()

        if profile_created:
            user.username = ""
            user.save()

            UserProfile.objects.create(
                user=user,
                full_name=name,
                profile_picture=picture
            )
