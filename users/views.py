from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import logout
from django.conf import settings
from django.core.paginator import Paginator
from django.utils.timezone import now
from django.urls import reverse
from django.core.cache import cache
from django.contrib import messages
from datetime import datetime, timedelta
from django.db.models import F,Sum,Q,Count
import pycountry
import os
from pathlib import Path
import requests
from django.utils.text import slugify  
from blog.models import Post, Category, Comment, CommentReply
from users.models import User, UserProfile, UserPostActivity, PostInteraction
from recommend.utils import get_user_recommendations, get_trending_posts_by_score
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
import json
from django.views.decorators.http import require_POST
from django.http import JsonResponse,HttpResponseRedirect

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
        
        # Get posts with annotated interaction counts
        recent_posts = Post.objects.filter(
            created_at__date__range=(week_ago, today)
        ).annotate(
            ann_view_count=Count('interactions', filter=Q(interactions__viewed=True)),
            ann_like_count=Count('interactions', filter=Q(interactions__liked=True)),
            ann_comment_count=Count('comments')
        )


        category_scores = {}
        category_posts = {}

        for post in recent_posts:
            days_old = max((today - post.created_at.date()).days, 1)
            # Calculate score using the annotated counts
            score = (post.ann_view_count + post.ann_like_count * 2 + post.ann_comment_count * 1.5) / days_old
            cid = post.category_id

            category_scores.setdefault(cid, []).append(score)
            category_posts.setdefault(cid, []).append((score, post))

        # Get all categories in one query
        categories = Category.objects.in_bulk(category_scores.keys())

        category_avg = [
            (sum(scores) / len(scores), categories[cid])
            for cid, scores in category_scores.items()
            if scores  # Ensure we don't divide by zero
        ]

        sorted_categories = sorted(category_avg, key=lambda x: x[0], reverse=True)

        category_post_map = [
            (cat, [p[1] for p in sorted(category_posts[cat.id], key=lambda x: x[0], reverse=True)[:3]])
            for _, cat in sorted_categories
        ]

        cache.set('trending_category_map', category_post_map, timeout=10800)

    # Handle user session and profile checks
    user, profile = get_user_and_profile(request.session)
    categories = Category.objects.all().order_by('name')

    if user:
        if not user.username:
            return redirect('profile_dtl')
        if not all([profile.gender, profile.birth_date, profile.location]):
            return redirect('other_dtl')
        if profile.category_preferences.count() < 3:
            return redirect('interest_selection')
    
    return render(request, 'index.html', {
        'category_post_map': category_post_map,
        'categories': categories,
        'user': user if user else None
    })


def trending_category_view(request, category_slug):
    category = get_object_or_404(Category, name__iexact=category_slug.replace('-', ' '))
    
    # Updated to use the utility function with annotations
    posts = get_trending_posts_by_score(category=category, days=7)
    page_obj = paginate(request, posts, per_page=9)
    categories = Category.objects.all().order_by('name')

    return render(request, 'trending_category.html', {
        'category': category,
        'page_obj': page_obj,
        'categories': categories,
    })

def for_you_view(request):
    if not request.user.is_authenticated:
        return redirect('/')
    
    user = request.user
    profile = getattr(user, 'profile', None)
    selected_tab = request.GET.get('tab', 'for_you')

    interest_categories = []
    if profile and profile.category_preferences.exists():
        interest_categories = list(profile.category_preferences.all().order_by('name'))

    if selected_tab == 'for_you':
        # This already uses the updated recommendation system
        posts = get_user_recommendations(user, top_n=30)
    else:
        category = next(
            (c for c in interest_categories if slugify(c.name) == selected_tab),
            None
        )
        if category:
            posts = get_trending_posts_by_score(category=category, days=7)
        else:
            posts = []

    page_obj = paginate(request, posts, per_page=9)

    return render(request, 'for_you.html', {
        'page_obj': page_obj,
        'selected_tab': selected_tab,
        'interest_categories': interest_categories,
    })


def following_posts(request):
    if not request.user.is_authenticated:
        return redirect('/')
    # Get the current user's profile
    profile = request.user.profile
    
    # Get all posts from followed users
    posts = profile.following_posts
    
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
    user = get_object_or_404(User, username=username)

    # Get all posts by this user
    posts = Post.objects.filter(user=user).order_by('-created_at')

    # Dynamic stats
    total_blogs = posts.count()
    total_likes = PostInteraction.objects.filter(post__in=posts, liked=True).count()

    # Fallback avatar (letter-based)
    profile_picture = user.profile.profile_picture
    if not profile_picture:
        first_letter = user.username[0].upper() if user.username else "U"
        profile_picture = f"https://ui-avatars.com/api/?name={first_letter}&background=0D8ABC&color=fff&size=128"

    # Pagination
    page_obj = paginate(request, posts, per_page=6)

    is_following = False
    
    if request.user.is_authenticated and request.user != user:
        is_following = request.user.profile.is_following(user.profile)
    
    categories=Category.objects.all().order_by('name')
    return render(request, 'user_profile.html', {
        'profile_user': user,
        'is_following': is_following,
        'page_obj': page_obj,
        'total_blogs': total_blogs,
        'total_likes': total_likes,
        'profile_picture': profile_picture,
        'categories':categories
    })



def post_detail_view(request, post_id):
    categories = Category.objects.all().order_by('name')
    post = get_object_or_404(Post, id=post_id)
    comments = post.comments.all().order_by('created_at')

    profile_user = get_object_or_404(User, username=post.user.username)

     # Record the view
    if request.user.is_authenticated:
        interaction, created = PostInteraction.objects.get_or_create(user=request.user, post=post)
        if not interaction.viewed:
            interaction.viewed = True
            interaction.save()


    is_following = False
    is_liked = False
    is_saved = False

    if request.user.is_authenticated:
        try:
            interaction = PostInteraction.objects.get(user=request.user, post=post)
            is_liked = interaction.liked
        except PostInteraction.DoesNotExist:
            pass

        is_saved = post in request.user.profile.saved_posts.all()

        if post.user != request.user:
            is_following = request.user.profile.is_following(post.user.profile)

   
    return render(request, 'post_detail.html', 
            {
                'post': post, 
                'comments': comments,
                'categories':categories,
                'is_following': is_following,
                'is_liked':is_liked,
                'is_saved':is_saved,
                'profile_user':profile_user
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
    
    categories = Category.objects.all().order_by('name')

    return render(request, 'newUserOtherDtl.html', {
        'user': user,
        'profile': profile,
        'countries': countries,
        'categories':categories
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
            print(moderation_data)
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
@csrf_exempt
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
                ext = Path(image.name).suffix
                filename = f"{user.id}_{datetime.now().strftime('%Y%m%d%H%M%S')}{ext}"
                path = os.path.join('images', 'blogs', filename)
                full_path = os.path.join(settings.MEDIA_ROOT, path)
                os.makedirs(os.path.dirname(full_path), exist_ok=True)
                with open(full_path, 'wb+') as f:
                    for chunk in image.chunks():
                        f.write(chunk)
                image_url = os.path.join('images', 'blogs', filename).replace("\\", "/")

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
                ext = Path(image.name).suffix
                filename = f"{request.user.id}_{datetime.now().strftime('%Y%m%d%H%M%S')}{ext}"
                path = os.path.join('images', 'blogs', filename)
                full_path = os.path.join(settings.MEDIA_ROOT, path)
                
                os.makedirs(os.path.dirname(full_path), exist_ok=True)
                with open(full_path, 'wb+') as f:
                    for chunk in image.chunks():
                        f.write(chunk)
                
                # Delete old image if exists
                if post.image_url:
                    old_path = os.path.join(settings.MEDIA_ROOT, post.image_url)
                    if os.path.exists(old_path):
                        os.remove(old_path)
                
                image_url = os.path.join('images', 'blogs', filename).replace("\\", "/")
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
        if post.image_url:
            image_path = os.path.join(settings.MEDIA_ROOT, post.image_url)
            if os.path.exists(image_path):
                os.remove(image_path)
        
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
    interaction, created = PostInteraction.objects.get_or_create(user=request.user, post=post)
    
    interaction.liked = not interaction.liked
    interaction.save()

    return JsonResponse({
        'status': 'liked' if interaction.liked else 'unliked',
        'like_count': post.like_count
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
    posts = request.user.profile.saved_posts.order_by('-created_at')
    categories = Category.objects.all().order_by('name')

    return render(request, 'saved_post.html', {
        'posts': posts,
        'categories': categories,
    })

@login_required
def liked_posts_view(request):
    interactions = PostInteraction.objects.filter(user=request.user, liked=True).select_related('post').order_by('-timestamp')
    liked_posts = [interaction.post for interaction in interactions]

    categories = Category.objects.all().order_by('name')

    return render(request, 'liked_posts.html', {
        'posts': liked_posts,
        'categories': categories,
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
