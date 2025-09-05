from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import logout
from django.conf import settings
from django.core.paginator import Paginator
from django.utils.timezone import now
from django.urls import reverse
from django.core.cache import cache
from django.contrib import messages
from datetime import datetime, timedelta
from django.db.models import Count, Q, F, ExpressionWrapper, FloatField
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.http import JsonResponse, HttpResponseRedirect
from blog.models import Post, Category, Comment, CommentReply, RecommendationLog
from users.models import UserProfile, PostInteraction, UserPostActivity, User, PostReport
from recommend.utils import (
    get_user_recommendations,
    get_trending_posts
)
import os
from pathlib import Path
import requests
import json
from django.utils.text import slugify
import time
import cloudinary

def paginate(request, items, per_page=9):
    """Optimized pagination with prefetch"""
    paginator = Paginator(items, per_page)
    page = request.GET.get('page')
    return paginator.get_page(page)

def get_user_and_profile(session):
    user_id = session.get('user_id')
    if not user_id:
        return None, None
    try:
        user = User.objects.get(id=user_id)
        if not user.is_authenticated or user.is_staff:
            return None, None
        profile, _ = UserProfile.objects.get_or_create(user=user)
        return user, profile
    except User.DoesNotExist:
        session.pop('user_id', None) 
        return None, None

def get_profile_or_none(user):
    """
    Return profile for non-staff authenticated users.
    Return None otherwise.
    """
    if not user or not user.is_authenticated or user.is_staff:
        return None
    try:
        return user.profile
    except UserProfile.DoesNotExist:
        return None

def index(request):
    categories = Category.objects.all().order_by('name')
    category_post_map = []
    
    for cat in categories:
        # First try with strict trending criteria
        posts = get_trending_posts(category=cat, days=7, top_n=3)
        
        # If empty, relax the requirements
        if not posts.exists():
            posts = get_trending_posts(category=cat, days=60, top_n=3)
        
        if posts.exists():
            category_post_map.append((cat, posts))
    
    context = {
        'category_post_map': category_post_map,
        'categories': categories,
        'user': request.user if request.user.is_authenticated else None
    }

    # User onboarding checks (only for non-staff users)
    if request.user.is_authenticated and not request.user.is_staff:
        profile, _ = UserProfile.objects.get_or_create(user=request.user)

        if not request.user.username:
            return redirect('profile_dtl')
        if not all([profile.gender, profile.birth_date, profile.location]):
            return redirect('other_dtl')
        if profile.category_preferences.count() < 3:
            return redirect('interest_selection')

    return render(request, 'index.html', context)

def trending_category_view(request, category_slug):
    category = get_object_or_404(Category, name__iexact=category_slug)
    
    # Updated to use the utility function with annotations
    # posts = get_trending_posts(category=category, days=7)

    posts = get_trending_posts(category=category, days=7)
    if not posts.exists():
        posts = get_trending_posts(category=category, days=30)
    if not posts.exists():
        posts = get_trending_posts(category=category, days=None)
            
    # page_obj = paginate(request, category_post_map, per_page=9)
    categories = Category.objects.all().order_by('name')

    return render(request, 'trending_category.html', {
        'category': category,
        'page_obj': paginate(request, posts),
        'categories': Category.objects.all().order_by('name')
    })

@login_required
def for_you_view(request):
    user = request.user
    profile = get_profile_or_none(request.user)
    if not profile:
        return redirect('/')
        
    # print(profile)
    selected_tab = request.GET.get('tab', 'for_you')
    start_time = time.time()

    fallback_posts = cache.get(f'user_fallback_{user.id}')
    if not fallback_posts:
        fallback_posts = Post.objects.filter(is_suspended=False).order_by('-created_at')[:30]
        cache.set(f'user_fallback_{user.id}', fallback_posts, 86400)

    if selected_tab == 'for_you':
        try:
            posts = get_user_recommendations(user, top_n=30)
            elapsed = time.time() - start_time

            # Use last known good recommendation if current took too long
            if elapsed > 2.0:
                print(f"⚠️ Recommender slow ({elapsed:.2f}s), using cache fallback.")
                posts = cache.get(f'user_recs_{user.id}_cached', fallback_posts)
        except Exception as e:
            print(f"🛑 Recommendation error: {str(e)}")
            posts = fallback_posts

        # Save for next time (if successful)
        if posts:
            cache.set(f'user_recs_{user.id}_cached', posts, 1800)

    else:
        # Handle category-based tab
        cache_key = f'user_categories_{user.id}'
        categories = cache.get(cache_key)

        if not categories:
            categories = list(profile.category_preferences.all().order_by('name'))
            cache.set(cache_key, categories, 3600)

        category = next(
            (c for c in categories if slugify(c.name.lower()) == selected_tab.lower()), 
            None
        )

        if category:
            posts = get_trending_posts(category=category, days=7)
            if not posts.exists():
                posts = cache.get(f'category_posts_{category.id}')
                if not posts:
                    posts = Post.objects.filter(category=category).order_by('-created_at')[:30]
                    cache.set(f'category_posts_{category.id}', posts, 3600)
        else:
            posts = Post.objects.none()

    # Ensure always fallback-ready
    if not posts or not posts.exists():
        posts = fallback_posts

    return render(request, 'for_you.html', {
        'page_obj': paginate(request, posts),
        'selected_tab': selected_tab,
        'interest_categories': profile.category_preferences.all().order_by('name')
    })


def following_posts(request):
    if not request.user.is_authenticated:
        return redirect('/')
    # Get the current user's profile
    profile = get_profile_or_none(request.user)
    if not profile:
        return redirect('/')
    
    # Get all posts from followed users
    posts = profile.following_posts.filter(is_suspended=False)
    
    # Filter by specific user if requested
    username = request.GET.get('user')
    if username:
        posts = posts.filter(user__username=username)
    
    # Pagination
    paginator = Paginator(posts, 10)  
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    categories=Category.objects.all().order_by('name')
    
    context = {
        'posts': page_obj,
        'followed_users': profile.followed_users.all(),
        'page_obj': page_obj,  
        'categories':categories
    }
    return render(request, 'following_posts.html', context)

@login_required
def follow_unfollow_user(request, username):
    target_user = get_object_or_404(User, username=username)
    target_profile = target_user.profile
    current_profile = request.user.profile
    
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'follow':
            current_profile.follow_user(target_profile)
            followed = True
        elif action == 'unfollow':
            current_profile.unfollow_user(target_profile)
            followed = False
        else:
            return JsonResponse({'status': 'error', 'message': 'Invalid action'}, status=400)
        
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({
                'status': 'success',
                'followed': followed,
                'follower_count': target_profile.followers_count
            })
        
        return redirect('user_profile', username=username)
    
    return JsonResponse({'status': 'error', 'message': 'Invalid request'}, status=400)

def user_profile_view(request, username):
    """Optimized profile view with counts"""
    user = get_object_or_404(User, username=username)
    posts = Post.objects.filter(user=user, is_suspended=False).order_by('-created_at')
    
    # Single query for all counts
    stats = posts.aggregate(
        total_blogs=Count('id'),
        total_likes=Count('interactions', filter=Q(interactions__liked=True))
    )
    
    return render(request, 'user_profile.html', {
        'profile_user': user,
        'page_obj': paginate(request, posts, 6),
        'is_following': request.user.profile.is_following(user.profile) if request.user.is_authenticated else False,
        **stats
    })

def post_detail_view(request, post_id):
    categories = Category.objects.all().order_by('name')
    post = get_object_or_404(Post, id=post_id)
    if post.is_suspended:
        messages.error(request, "This post has been suspended.")
        return redirect('/')
    comments = post.comments.all().order_by('created_at')

    profile_user = get_object_or_404(User, username=post.user.username)

     # Record the view
    if request.user.is_authenticated and not request.user.is_staff:
        interaction, created = PostInteraction.objects.get_or_create(user=request.user, post=post)
        if not interaction.viewed:
            interaction.viewed = True
            interaction.save()
            
        if interaction.viewed:
            RecommendationLog.objects.filter(user=request.user, post=post).update(clicked=True)


    is_following = False
    is_liked = False
    is_saved = False

    profile = get_profile_or_none(request.user)

    if profile:
        try:
            interaction = PostInteraction.objects.get(user=request.user, post=post)
            is_liked = interaction.liked
        except PostInteraction.DoesNotExist:
            pass

        is_saved = post in profile.saved_posts.all()

        post_user_profile = get_profile_or_none(post.user)
        if post_user_profile and post.user != request.user:
            is_following = profile.is_following(post_user_profile)

    return render(
        request,
        'post_detail.html',
        {
            'post': post,
            'comments': comments,
            'categories': categories,
            'is_following': is_following,
            'is_liked': is_liked,
            'is_saved': is_saved,
            'profile_user': profile_user,
        }
    )


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
            # filename = f"{user.id}_{datetime.now().strftime('%Y%m%d%H%M%S')}.jpg"
            # relative_path = os.path.join('images', 'users_profile_pic', filename)
            # absolute_path = os.path.join(settings.MEDIA_ROOT, relative_path)

            # os.makedirs(os.path.dirname(absolute_path), exist_ok=True)
            # with open(absolute_path, 'wb+') as dest:
            #     for chunk in profile_picture.chunks():
            #         dest.write(chunk)

            # profile.profile_picture = os.path.join('images', 'users_profile_pic', filename).replace('\\', '/')
            # changed = True
            try:
                upload_result = cloudinary.uploader.upload(
                    profile_picture,
                    folder="blognest_profile_pictures"
                )
                profile.profile_picture = upload_result['secure_url']
            except Exception as e:
                messages.error(request, f"Error uploading profile picture: {str(e)}")
            changed = True

        if changed:
            user.save()
            profile.save()

        return redirect('other_dtl')

    categories = Category.objects.all().order_by('name')
    return render(request, 'newUserProfileDtl.html', {
        'user': user,
        'initial_data': {
            'email': user.email,
            'username': user.username,
            'full_name': profile.full_name,
            'profile_picture': profile.profile_picture,
            'categories': categories
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
        'countries': countries,
    })

def interest_selection_view(request):
    user, profile = get_user_and_profile(request.session)
    if not user:
        return redirect('/')

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
        'selected_ids': profile.category_preferences.values_list('id', flat=True),
    })

def validate_content(content, min_words=200, max_words=2000, min_paragraphs=2):
    """Validate content meets minimum requirements"""
    word_count = len(content.split())
    # print(word_count)
    if word_count < min_words:
        return False, f"Content too short (minimum {min_words} words required)"
    if word_count > max_words:
        return False, f"Content too long (maximum {max_words} words allowed)"
    return True, ""

def moderate_blog_content(title, content, category):
    """Improved moderation with better relevance checking"""
    prompt = f"""
You are a content moderation AI for a computer science technology platform. 
Evaluate if the content is relevant to the category by considering:

1. Technical accuracy (40% weight)
2. Category relevance (30% weight)
3. Educational value (20% weight)
4. Appropriate language (10% weight)

Return ONLY a JSON response with these keys:
- "verdict": "APPROVED" or "REJECTED"
- "relevance_score": percentage (0-100)
- "reason": brief explanation

---
Title: {title}
Category: {category}
Content Excerpt:
{content[:1500]}...
---

Analyze the full context, not just keywords. Even if the title seems relevant, 
reject if the content doesn't match the category's technical focus.
"""
    try:
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.OPENROUTER_API_KEY_SECRET}",
                "Content-Type": "application/json",
                "X-Title": "Content Moderation"
            },
            json={
                "model": "mistralai/mistral-7b-instruct",
                "response_format": {"type": "json_object"},
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.3  
            },
        )
        result = response.json()
        moderation = result['choices'][0]['message']['content']
        
        try:
            moderation_data = json.loads(moderation)
            # print(moderation_data)
            if moderation_data.get('relevance_score', 0) >= 40:
                return "APPROVED", moderation_data.get('reason', 'Content meets requirements')
            return f"REJECTED", {moderation_data.get('reason', 'Not relevant enough')}
        except json.JSONDecodeError:
            # Fallback if JSON parsing fails
            verdict = moderation.strip().upper()
            if "APPROVED" in verdict:
                return "APPROVED", "Content approved"
            return "REJECTED", "Unable to verify content relevance"

    except Exception as e:
        print(f"🛑 AI moderation failed: {str(e)}")
        return "REJECTED: Moderation system error", str(e)

@login_required
def write_post_view(request):
    user = request.user
    categories = Category.objects.all()

    if request.method == 'POST':
        title = request.POST.get('title', '').strip()
        content = request.POST.get('content', '').strip()
        category_id = request.POST.get('category')
        image = request.FILES.get('thumbnail')

        # Basic validation
        if not title or not content or not category_id:
            messages.error(request, "Please fill all required fields")
            return render(request, 'write_post.html', {
                'categories': categories,
                'title': title,
                'content': content,
                'selected_category': category_id
            })

        category = get_object_or_404(Category, id=category_id)

        # Content length validation
        is_valid, validation_msg = validate_content(content)
        if not is_valid:
            messages.error(request, validation_msg)
            return render(request, 'write_post.html', {
                'categories': categories,
                'title': title,
                'content': content,
                'selected_category': category.id
            })

        # 🔍 AI Moderation
        verdict, reason = moderate_blog_content(title, content, category.name)
        if not verdict.startswith("APPROVED"):
            messages.error(request, verdict+""+str(reason) if reason else verdict)
            return render(request, 'write_post.html', {
                'categories': categories,
                'title': title,
                'content': content,
                'selected_category': category.id
            })

        # 🖼️ Image Handling
        image_url = None
        if image:
            # Validate image
            if image.size > 5*1024*1024:  # 5MB limit
                messages.error(request, "Image too large (max 5MB)")
                return render(request, 'write_post.html', {
                    'categories': categories,
                    'title': title,
                    'content': content,
                    'selected_category': category.id
                })
            try:
                # result = cloudinary.uploader.upload(image)
                # post.image_url = result['secure_url']
                upload_result = cloudinary.uploader.upload(
                    image,
                    folder="blognest_images"  
                )
                image_url = upload_result['secure_url']
                

            except Exception as e:
                messages.error(request, f"Error saving image: {str(e)}")
                return render(request, 'write_post.html', {
                    'categories': categories,
                    'title': title,
                    'content': content,
                    'selected_category': category.id
                })

        # ✅ Save Blog
        try:
            post = Post.objects.create(
                user=user,
                title=title,
                content=content,
                category=category,
                image_url=image_url
            )

            UserPostActivity.objects.create(
                user=user,
                post=post,
                action='A',
                details="POST Added",
            )
            return redirect('post_detail', post_id=post.id)
        except Exception as e:
            messages.error(request, f"Error saving blog: {str(e)}")
        
    return render(request, 'write_post.html', {'categories': categories})


@login_required
def edit_post_view(request, post_id):
    post = get_object_or_404(Post, id=post_id, user=request.user)
    categories = Category.objects.all().order_by('name')
    
    if request.method == 'POST':
        title = request.POST.get('title', '').strip()
        content = request.POST.get('content', '').strip()
        category_id = request.POST.get('category')
        image = request.FILES.get('thumbnail')
        reason = request.POST.get('reason', 'other')
        details = request.POST.get('details', '').strip()
        
        # Validation
        if not title or not content or not category_id:
            messages.error(request, "Please fill all required fields")
            return render(request, 'write_post.html', {
                'REASON_CHOICES': UserPostActivity.REASON_CHOICES,
                'categories': categories,
                'title': title,
                'content': content,
                'selected_category': category_id,
                'post': post,
                'editing': True
            })
            
        if not reason:
            messages.error(request, "Please select a reason for editing")
            return render(request, 'write_post.html', {
                'REASON_CHOICES': UserPostActivity.REASON_CHOICES,
                'categories': categories,
                'title': title,
                'content': content,
                'selected_category': category_id,
                'post': post,
                'editing': True
            })
            
        if reason == 'other' and not details:
            messages.error(request, "Please provide details for your edit")
            return render(request, 'write_post.html', {
                'REASON_CHOICES': UserPostActivity.REASON_CHOICES,
                'categories': categories,
                'title': title,
                'content': content,
                'selected_category': category_id,
                'post': post,
                'editing': True
            })
        
        category = get_object_or_404(Category, id=category_id)
        
        # Content validation
        is_valid, validation_msg = validate_content(content)
        if not is_valid:
            messages.error(request, validation_msg)
            return render(request, 'write_post.html', {
                'REASON_CHOICES': UserPostActivity.REASON_CHOICES,
                'categories': categories,
                'title': title,
                'content': content,
                'selected_category': category.id,
                'post': post,
                'editing': True
            })
        
        # Moderation check
        verdict, reason = moderate_blog_content(title, content, category.name)
        if not verdict.startswith("APPROVED"):
            messages.error(request, f"Content not approved: {reason}")
            return render(request, 'write_post.html', {
                'REASON_CHOICES': UserPostActivity.REASON_CHOICES,
                'categories': categories,
                'title': title,
                'content': content,
                'selected_category': category.id,
                'post': post,
                'editing': True
            })
        
        # Image handling
        image_url = post.image_url
        if image:
            if image.size > 5*1024*1024:
                messages.error(request, "Image too large (max 5MB)")
                return render(request, 'write_post.html', {
                    'REASON_CHOICES': UserPostActivity.REASON_CHOICES,
                    'categories': categories,
                    'title': title,
                    'content': content,
                    'selected_category': category.id,
                    'post': post,
                    'editing': True
                })
                
            try:
                # ext = Path(image.name).suffix
                # filename = f"{request.user.id}_{datetime.now().strftime('%Y%m%d%H%M%S')}{ext}"
                # path = os.path.join('images', 'blogs', filename)
                # full_path = os.path.join(settings.MEDIA_ROOT, path)
                
                # os.makedirs(os.path.dirname(full_path), exist_ok=True)
                # with open(full_path, 'wb+') as f:
                #     for chunk in image.chunks():
                #         f.write(chunk)
                
                # # Delete old image if exists
                # if post.image_url:
                #     old_path = os.path.join(settings.MEDIA_ROOT, post.image_url)
                #     if os.path.exists(old_path):
                #         os.remove(old_path)
                
                # image_url = os.path.join('images', 'blogs', filename).replace("\\", "/")
                upload_result = cloudinary.uploader.upload(
                    image,
                    folder="blognest_images"  
                )
                image_url = upload_result['secure_url']
            except Exception as e:
                messages.error(request, f"Error saving image: {str(e)}")
                return render(request, 'write_post.html', {
                    'REASON_CHOICES': UserPostActivity.REASON_CHOICES,
                    'categories': categories,
                    'title': title,
                    'content': content,
                    'selected_category': category.id,
                    'post': post,
                    'editing': True
                })
        
        # Update post
        try:
            post.title = title
            post.content = content
            post.category = category
            post.image_url = image_url
            post.save()
            
            # Record activity
            UserPostActivity.objects.create(
                user=request.user,
                post=post,
                action='E',
                reason=reason,
                details=details
            )
            
            # messages.success(request, "Post updated successfully!")
            return redirect('post_detail', post_id=post.id)
            
        except Exception as e:
            messages.error(request, f"Error updating post: {str(e)}")
    
    return render(request, 'write_post.html', {
        'REASON_CHOICES': UserPostActivity.REASON_CHOICES,
        'categories': categories,
        'title': post.title,
        'content': post.content,
        'selected_category': post.category.id,
        'post': post,
        'editing': True
    })

@login_required
@require_POST
def delete_post_view(request, post_id):
    post = get_object_or_404(Post, id=post_id, user=request.user)
    details = request.POST.get('details', '').strip()

    try:
        # Record activity before deletion
        UserPostActivity.objects.create(
            user=request.user,
            post=post,
            action='D',
            reason="POST DELETED",
            details=details
        )
        
        # Delete image if exists
        # if post.image_url:
        #     image_path = os.path.join(settings.MEDIA_ROOT, post.image_url)
        #     if os.path.exists(image_path):
        #         os.remove(image_path)
        if post.image_url and 'res.cloudinary.com' in post.image_url:
            try:
                # Extract public_id from URL
                public_id = post.image_url.split('/')[-1].split('.')[0]
                cloudinary.uploader.destroy(public_id)
            except Exception as e:
                # Log the error but continue with post deletion
                print(f"Error deleting Cloudinary image: {str(e)}")
                
        post.delete()
        # messages.success(request, "Post deleted successfully!")
        return redirect('user_profile', username=request.user.username)
        
    except Exception as e:
        messages.error(request, f"Error deleting post: {str(e)}")
        return redirect('post_detail', post_id=post.id)
    
@require_POST
@login_required
def toggle_like(request, post_id):
    post = get_object_or_404(Post, id=post_id)
    interaction, created = PostInteraction.objects.get_or_create(
        user=request.user, 
        post=post
    )
    
    # Toggle the like status
    interaction.liked = not interaction.liked
    interaction.save()

    if interaction.liked:
        RecommendationLog.objects.filter(user=request.user, post=post).update(engaged=True)
    # Return the fresh count from the database
    return JsonResponse({
        'status': 'liked' if interaction.liked else 'unliked',
        'like_count': post.like_count  # Using the property
    })

@require_POST
@login_required
def toggle_save(request, post_id):
    post = get_object_or_404(Post, id=post_id)

    interaction, created = PostInteraction.objects.get_or_create(user=request.user, post=post)
    
    interaction.saved = not interaction.saved
    interaction.save()

    profile = request.user.profile

    if post in profile.saved_posts.all():
        profile.saved_posts.remove(post)
        status = "unsaved"
    else:
        profile.saved_posts.add(post)
        status = "saved"

    return JsonResponse({"status": status})

@login_required
def saved_posts_view(request):
    posts = request.user.profile.saved_posts.filter(is_suspended=False).order_by('-created_at')
    return render(request, 'saved_post.html', {
        'posts': posts,
    })

@login_required
def liked_posts_view(request):
    interactions = PostInteraction.objects.filter(user=request.user, liked=True).select_related('post').order_by('-timestamp')
    liked_posts = [interaction.post for interaction in interactions if not interaction.post.is_suspended]

    return render(request, 'liked_posts.html', {
        'posts': liked_posts,
    })

@login_required
def add_comment(request, post_id):
    if request.method == 'POST':
        post = get_object_or_404(Post, id=post_id)
        text = request.POST.get('comment_text')
        if text:
            Comment.objects.create(post=post, user=request.user, text=text)
    return redirect('post_detail', post_id=post_id)


@login_required
def add_reply(request, comment_id):
    if request.method == 'POST':
        comment = get_object_or_404(Comment, id=comment_id)
        text = request.POST.get('reply_text')
        if text:
            reply = CommentReply.objects.create(
                comment=comment,
                parent_comment=comment,
                user=request.user,
                text=text
            )
            return JsonResponse({
                'status': 'success',
                'reply': {
                    'id': reply.id,
                    'text': reply.text,
                    'username': reply.user.username,
                    'created_at': reply.created_at.strftime('%b %d, %Y %I:%M %p'),
                    'delete_url': reverse('delete_reply', args=[reply.id])
                }
            })
    return JsonResponse({'status': 'error'}, status=400)


@require_POST
@login_required
def inline_edit_comment(request, comment_id):
    comment = get_object_or_404(Comment, id=comment_id, user=request.user)
    
    if not comment.is_editable:
        return JsonResponse({'status': 'error', 'message': 'Editing time expired'}, status=403)
    
    text = request.POST.get('text', '').strip()
    if not text:
        return JsonResponse({'status': 'error', 'message': 'Text cannot be empty'}, status=400)
    
    comment.text = text
    comment.save()
    return JsonResponse({'status': 'success', 'text': comment.text})


@login_required
def delete_comment(request, comment_id):
    comment = get_object_or_404(Comment, id=comment_id, user=request.user)
    if not comment.is_editable:
        messages.error(request, "Comment can only be deleted within 24 hours.")
        return redirect('post_detail', post_id=comment.post.id)

    post_id = comment.post.id
    comment.delete()
    # messages.success(request, "Comment deleted.")
    return HttpResponseRedirect(
        reverse('post_detail', args=[post_id]) + '#comments-section'
    )


@require_POST
@login_required
def inline_edit_reply(request, reply_id):
    reply = get_object_or_404(CommentReply, id=reply_id, user=request.user)
    if not reply.is_editable:
        return JsonResponse({'status': 'error', 'message': 'Editing time expired'}, status=403)

    text = request.POST.get('text', '').strip()
    if not text:
        return JsonResponse({'status': 'error', 'message': 'Text cannot be empty'}, status=400)

    reply.text = text
    reply.save()
    return JsonResponse({'status': 'success', 'text': reply.text})


@login_required
def delete_reply(request, reply_id):
    reply = get_object_or_404(CommentReply, id=reply_id, user=request.user)
    if not reply.is_editable:
        messages.error(request, "Reply can only be deleted within 24 hours.")
        return redirect('post_detail', post_id=reply.comment.post.id)

    post_id = reply.comment.post.id
    reply.delete()
    # messages.success(request, "Reply deleted.")
    return HttpResponseRedirect(
        reverse('post_detail', args=[reply.comment.post.id]) + f'#comment-{reply.comment.id}'
    )

@require_POST
@login_required
def report_post(request, post_id):
    try:
        post = Post.objects.get(id=post_id)
        reason = request.POST.get("reason")

        if not reason:
            return JsonResponse({"success": False, "message": "Reason required."}, status=400)

        # Prevent duplicate reports by same user on same post
        report, created = PostReport.objects.get_or_create(
            post=post, user=request.user, defaults={"reason": reason}
        )

        if not created:
            return JsonResponse({"success": False, "message": "You already reported this post."})

        return JsonResponse({"success": True, "message": "Report submitted successfully."})

    except Post.DoesNotExist:
        return JsonResponse({"success": False, "message": "Post not found."}, status=404)