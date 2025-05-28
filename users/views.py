from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import logout
from django.conf import settings
from django.core.paginator import Paginator
from django.utils.timezone import now
from django.core.cache import cache
from django.contrib import messages
from datetime import datetime, timedelta
from django.db.models import F
import pycountry
import os

from blog.models import Post, Category, Comment
from users.models import User, UserProfile
from recommend.utils import get_user_recommendations, get_trending_posts_by_score

def paginate(request, queryset, per_page=9):
    paginator = Paginator(queryset, per_page)
    page = request.GET.get('page')
    return paginator.get_page(page)

def get_user_and_profile(session):
    user_id = session.get('user_id')
    if not user_id:
        return None, None

    try:
        user = User.objects.get(id=user_id)
        profile, _ = UserProfile.objects.get_or_create(user=user)
        return user, profile
    except User.DoesNotExist:
        del session['user_id']
        return None, None


def index(request):
    category_post_map = cache.get('trending_category_map')

    if not category_post_map:
        today = now().date()
        week_ago = today - timedelta(days=7)
        recent_posts = Post.objects.filter(created_at__date__range=(week_ago, today))

        category_scores, category_posts = {}, {}

        for post in recent_posts:
            days_old = max((today - post.created_at.date()).days, 1)
            score = post.views_count / days_old
            cid = post.category_id

            category_scores.setdefault(cid, []).append(score)
            category_posts.setdefault(cid, []).append((score, post))

        category_avg = [
            (sum(scores) / len(scores), Category.objects.get(id=cid))
            for cid, scores in category_scores.items()
        ]

        sorted_categories = sorted(category_avg, key=lambda x: x[0], reverse=True)

        category_post_map = [
            (cat, [p[1] for p in sorted(category_posts[cat.id], key=lambda x: x[0], reverse=True)[:3]])
            for _, cat in sorted_categories
        ]

        cache.set('trending_category_map', category_post_map, timeout=10800)

    user, profile = get_user_and_profile(request.session)
    categories = Category.objects.all().order_by('name')

    if user:
        if not user.username:
            return render(request, 'newUserProfileDtl.html', {'categories': categories})
        if not all([profile.gender, profile.birth_date, profile.location]):
            return render(request, 'newUserOtherDtl.html', {'categories': categories})
        if profile.category_preferences.count() < 3:
            return redirect('interest_selection')

    return render(request, 'index.html', {
        'category_post_map': category_post_map,
        'categories': categories,
        'user': user if user else None
    })

def trending_category_view(request, category_slug):
    category = get_object_or_404(Category, name__iexact=category_slug.replace('-', ' '))
    posts = get_trending_posts_by_score(category=category, days=7)
    page_obj = paginate(request, posts, per_page=9)
    categories = Category.objects.all().order_by('name')

    return render(request, 'trending_category.html', {
        'category': category,
        'page_obj': page_obj,
        'categories': categories,
    })

def for_you_view(request):
    posts = get_user_recommendations(request.user, top_n=30)
    page_obj = paginate(request, posts)
    return render(request, 'for_you.html', {'page_obj': page_obj})


def category_view(request, category_slug):
    category = get_object_or_404(Category, name__iexact=category_slug)

    if request.user.is_authenticated:
        recommended = get_user_recommendations(request.user, top_n=50)
        posts = [p for p in recommended if p.category == category]
    else:
        posts = Post.objects.filter(category=category).order_by('-created_at')

    page_obj = paginate(request, posts)
    return render(request, 'blog/category.html', {
        'category': category,
        'page_obj': page_obj,
    })


def user_profile_view(request, username):
    user = get_object_or_404(User, username=username)
    posts = Post.objects.filter(user=user).order_by('-created_at')
    page_obj = paginate(request, posts)
    return render(request, 'blog/user_profile.html', {
        'profile_user': user,
        'page_obj': page_obj,
    })


def post_detail_view(request, post_id):
    post = get_object_or_404(Post, id=post_id)
    comments = Comment.objects.filter(post=post).order_by('-created_at')
    return render(request, 'post_detail.html', {'post': post, 'comments': comments})


def logout_view(request):
    logout(request)
    request.session.flush()
    return redirect('/')


def profile_dtl(request):
    user, profile = get_user_and_profile(request.session)
    if not user:
        return redirect('/')

    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        full_name = request.POST.get('full_name', '').strip()
        profile_picture = request.FILES.get('profile_picture')

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

    return render(request, 'newUserProfileDtl.html', {
        'user': user,
        'initial_data': {
            'email': user.email,
            'username': user.username,
            'full_name': profile.full_name,
            'profile_picture': profile.profile_picture
        }
    })

def other_dtl(request):
    user, profile = get_user_and_profile(request.session)
    if not user:
        return redirect('/')

    countries = [country.name for country in pycountry.countries]

    if request.method == 'POST':
        profile.gender = request.POST.get('gender')
        profile.birth_date = request.POST.get('birth_date')
        profile.location = request.POST.get('location')
        profile.save()
        return redirect('interest_selection')

    return render(request, 'newUserOtherDtl.html', {
        'user': user,
        'profile': profile,
        'countries': countries
    })

def interest_selection_view(request):
    user, profile = get_user_and_profile(request.session)
    if not user:
        return redirect('/')

    categories = Category.objects.all().order_by('name')

    if request.method == 'POST':
        selected_ids = request.POST.getlist('categories')
        if len(selected_ids) < 3:
            messages.error(request, "Please select at least 3 interests.")
        else:
            profile.category_preferences.set(selected_ids)
            profile.save()
            return redirect('/')

    return render(request, 'interest_selection.html', {
        'user': user,
        'categories': categories,
        'selected_ids': profile.category_preferences.values_list('id', flat=True),
    })
