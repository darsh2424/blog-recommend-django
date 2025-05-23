from django.shortcuts import render, redirect
from django.contrib.auth import logout
from django.conf import settings
from users.models import User, UserProfile
from datetime import datetime
import os
import pycountry

def index(request):
    user_id = request.session.get('user_id')
    if user_id:
        try:
            user = User.objects.get(id=user_id)
            profile, _ = UserProfile.objects.get_or_create(user=user)

            if not user.username or user.username.strip() == "":
                return redirect('profile_dtl')

            if not profile.gender or not profile.birth_date or not profile.location:
                return redirect('other_dtl')

            return render(request, 'index.html', {'user': user})

        except User.DoesNotExist:
            del request.session['user_id']
            return redirect('/')

    return render(request, 'index.html')

def logout_view(request):
    logout(request)
    request.session.flush()
    return redirect('/')

def profile_dtl(request):
    user_id = request.session.get('user_id')
    if user_id:
        try:
            user = User.objects.get(id=user_id)
            profile, _ = UserProfile.objects.get_or_create(user=user)
        except User.DoesNotExist:
            del request.session['user_id']
            return redirect('/')
    else:
        return redirect('/')
    
    initial_data = {
        'email': user.email,
        'username': user.username,
        'full_name': profile.full_name,
        'profile_picture': profile.profile_picture,
    }

    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        full_name = request.POST.get('full_name', '').strip()
        profile_picture = request.FILES.get('profile_picture', None)

        changed = False

        if username and username != user.username:
            user.username = username
            changed = True

        if full_name and full_name != profile.full_name:
            profile.full_name = full_name
            changed = True

        if profile_picture and hasattr(profile_picture, 'name') and profile_picture.name.strip():
            filename = f"{user.id}_{datetime.now().strftime('%Y%m%d%H%M%S')}.jpg"
            relative_path = os.path.join('images', 'users_profile_pic', filename)
            absolute_path = os.path.join(settings.MEDIA_ROOT, relative_path)

            os.makedirs(os.path.dirname(absolute_path), exist_ok=True)
            with open(absolute_path, 'wb+') as dest:
                for chunk in profile_picture.chunks():
                    dest.write(chunk)

            profile.profile_picture = os.path.join('images', 'users_profile_pic', filename).replace('\\', '/')
            changed = True

        if changed:
            user.save()
            profile.save()

        return redirect('other_dtl')

    return render(request, 'newUserProfileDtl.html', {'user': user, 'initial_data': initial_data})

def other_dtl(request):
    user_id = request.session.get('user_id')
    if user_id:
        try:
            user = User.objects.get(id=user_id)
            profile, _ = UserProfile.objects.get_or_create(user=user)
        except User.DoesNotExist:
            del request.session['user_id']
            return redirect('/')
    else:
        return redirect('/')

    countries = [country.name for country in pycountry.countries]

    if request.method == 'POST':
        profile.gender = request.POST.get('gender')
        profile.birth_date = request.POST.get('birth_date')
        profile.location = request.POST.get('location')
        profile.save()
        return redirect('/')  

    return render(request, 'newUserOtherDtl.html', {'user': user, 'countries': countries})
