from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib import messages
from django.db.models import Count, Q, Sum
from django.utils import timezone
from django.http import JsonResponse
from datetime import datetime, timedelta, date
from calendar import month_name
from django.db.models.functions import TruncDay, TruncWeek, TruncMonth
import json
from blog.models import Post, Category, Comment
from users.models import User, UserProfile, PostInteraction, UserPostActivity,PostReport


def get_granularity(start_date, end_date):
    days = (end_date - start_date).days
    if days <= 15:
        return 'day', TruncDay('created_at')
    elif days <= 150:
        return 'week', TruncWeek('created_at')
    return 'month', TruncMonth('created_at')

def get_granularity_timestamp(start_date, end_date):
    diff_days = (end_date - start_date).days
    if diff_days <= 15:
        return "daily", TruncDay("timestamp")
    elif diff_days <= 150:
        return "weekly", TruncWeek("timestamp")
    else:
        return "monthly", TruncMonth("timestamp")

# @staff_member_required
def mis_dashboard(request):
    return render(request, 'admin_management/dashboard.html')

# @staff_member_required
def chart_user_growth(request):
    start = request.GET.get('start')
    end = request.GET.get('end')
    if not start or not end:
        end_date = datetime.today().date()
        start_date = end_date - timedelta(days=6)
    else:
        start_date = datetime.strptime(start, "%Y-%m-%d").date()
        end_date = datetime.strptime(end, "%Y-%m-%d").date()

    granularity, trunc_func = get_granularity(start_date, end_date)

    data = (
        User.objects.filter(created_at__date__range=[start_date, end_date])
        .annotate(period=trunc_func)
        .values('period')
        .annotate(count=Count('id'))
        .order_by('period')
    )

    return JsonResponse(list(data), safe=False)

# @staff_member_required
def chart_daily_active_users(request):
    start = request.GET.get("start")
    end = request.GET.get("end")

    if not start or not end:
        end_date = datetime.today().date()
        start_date = end_date - timedelta(days=6)
    else:
        try:
            start_date = datetime.strptime(start, "%Y-%m-%d").date()
            end_date = datetime.strptime(end, "%Y-%m-%d").date()
            if start_date > end_date:
                return JsonResponse({"error": "Start date cannot be after end date."}, status=400)
        except ValueError:
            return JsonResponse({"error": "Invalid date format. Use YYYY-MM-DD."}, status=400)

    granularity, trunc_func = get_granularity_timestamp(start_date, end_date)

    data = (
        PostInteraction.objects.filter(timestamp__date__range=[start_date, end_date])
        .annotate(period=trunc_func)
        .values("period")
        .annotate(count=Count("user", distinct=True))
        .order_by("period")
    )

    # Convert period to string for JSON serialization
    data_list = [
        {"period": entry["period"].strftime("%Y-%m-%d"), "count": entry["count"]}
        for entry in data
    ]

    return JsonResponse({"granularity": granularity, "data": data_list})


# @staff_member_required
def chart_post_engagement(request):
    start = request.GET.get('start')
    end = request.GET.get('end')

    # Default: last 7 days
    if not start or not end:
        end_date = datetime.today().date()
        start_date = end_date - timedelta(days=6)
    else:
        start_date = datetime.strptime(start, "%Y-%m-%d").date()
        end_date = datetime.strptime(end, "%Y-%m-%d").date()

    granularity, trunc_func = get_granularity_timestamp(start_date, end_date)  # Use your existing helper

    data = (
        PostInteraction.objects
        .filter(timestamp__date__range=[start_date, end_date])
        .annotate(period=trunc_func)
        .values('period')
        .annotate(
            views=Count('id', filter=Q(viewed=True)),
            likes=Count('id', filter=Q(liked=True)),
            saves=Count('id', filter=Q(saved=True))
        )
        .order_by('period')
    )

    return JsonResponse(list(data), safe=False)

# @staff_member_required
def chart_top_posts(request):
    data = (
        Post.objects.annotate(view_count=Count('interactions'))
        .order_by('-view_count')[:7]
        .values('title', 'view_count')
    )
    return JsonResponse(list(data), safe=False)

# @staff_member_required
def chart_category_breakdown(request):
    data = (
        Category.objects.annotate(post_count=Count('posts'))
        .values('name', 'post_count')
    )
    return JsonResponse(list(data), safe=False)

# @staff_member_required
def chart_reports(request):
    end_date = datetime.today().date()
    start_date = end_date - timedelta(days=29)

    data = (
        PostReport.objects.filter(reported_at__date__range=[start_date, end_date])
        .annotate(period=TruncDay('reported_at'))
        .values('period')
        .annotate(count=Count('id'))
        .order_by('period')
    )

    return JsonResponse(list(data), safe=False)

# @staff_member_required
def manage_categories(request):
    """Manage Categories with counters"""
    categories = Category.objects.annotate(
        total_posts=Count('posts'),
        total_users_preference=Count('preferred_by_users', distinct=True)
    ).order_by('-total_posts')
    
    context = {
        'categories': categories,
        'active_section': 'categories'
    }
    return render(request, 'admin_management/manage_categories.html', context)

# @staff_member_required
def add_category(request):
    """Add new category"""
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        if name:
            category, created = Category.objects.get_or_create(name=name)
            if created:
                messages.success(request, f'Category "{name}" added successfully!')
            else:
                messages.warning(request, f'Category "{name}" already exists!')
        else:
            messages.error(request, 'Category name cannot be empty!')
    return redirect('manage_categories')

# @staff_member_required
def delete_category(request, category_id):
    """Delete category and move posts to 'Others'"""
    if request.method == 'POST':
        confirmation_text = request.POST.get('confirmation_text', '')
        expected_text = f"Delete Category {category_id}"
        
        if confirmation_text == expected_text:
            category = get_object_or_404(Category, id=category_id)
            
            # Create or get 'Others' category
            others_category, created = Category.objects.get_or_create(name='Others')
            
            # Move all posts to 'Others' category
            posts_moved = Post.objects.filter(category=category).update(category=others_category)
            
            category_name = category.name
            category.delete()
            
            messages.success(request, f'Category "{category_name}" deleted! {posts_moved} posts moved to "Others".')
        else:
            messages.error(request, 'Invalid confirmation text!')
            
    return redirect('manage_categories')

# @staff_member_required
def manage_posts(request):
    """Manage Posts with all counters and reports"""
    posts = Post.objects.select_related('user', 'category').annotate(
        annotated_likes_count=Count('interactions', filter=Q(interactions__liked=True)),
        annotated_views_count=Count('interactions', filter=Q(interactions__viewed=True)),
        annotated_comments_count=Count('comments'),
        annotated_reports_count=Count('admin_reports')
    ).order_by('-created_at')
    
    # Get report details for tooltips
    post_reports = {}
    for post in posts:
        if post.annotated_reports_count > 0:
            reports = PostReport.objects.filter(post=post).values('reason').annotate(
                count=Count('reason')
            ).order_by('-count')
            post_reports[post.id] = list(reports)
    
    context = {
        'posts': posts,
        'post_reports': post_reports,
        'active_section': 'posts'
    }
    return render(request, 'admin_management/manage_posts.html', context)

# @staff_member_required
def delete_post(request, post_id):
    """Delete post with confirmation"""
    if request.method == 'POST':
        confirmation_text = request.POST.get('confirmation_text', '')
        expected_text = f"Delete Post {post_id}"
        
        if confirmation_text == expected_text:
            post = get_object_or_404(Post, id=post_id)
            post_title = post.title
            post.delete()
            messages.success(request, f'Post "{post_title}" deleted successfully!')
        else:
            messages.error(request, 'Invalid confirmation text!')
            
    return redirect('manage_posts')

# @staff_member_required
def manage_users(request):
    """Manage Users with all counters and reports"""
    users = User.objects.select_related('profile').annotate(
        total_posts=Count('posts'),
        total_likes=Count('posts__interactions', filter=Q(posts__interactions__liked=True)),
        total_views=Count('posts__interactions', filter=Q(posts__interactions__viewed=True)),
        total_comments=Count('posts__comments'),
        reports_count=Count('posts__admin_reports'),
        unique_reports_count=Count('posts__admin_reports__reason', distinct=True)
    ).order_by('-total_posts')
    
    # Get report details for tooltips
    user_reports = {}
    for user in users:
        if user.reports_count > 0:
            reports = PostReport.objects.filter(post__user=user).values('reason').annotate(
                count=Count('reason')
            ).order_by('-count')
            user_reports[user.id] = list(reports)
    
    context = {
        'users': users,
        'user_reports': user_reports,
        'active_section': 'users'
    }
    return render(request, 'admin_management/manage_users.html', context)

# @staff_member_required
def delete_user(request, user_id):
    """Delete user with confirmation"""
    if request.method == 'POST':
        confirmation_text = request.POST.get('confirmation_text', '')
        expected_text = f"Delete User {user_id}"
        
        if confirmation_text == expected_text:
            user = get_object_or_404(User, id=user_id)
            username = user.username or user.email
            user.delete()
            messages.success(request, f'User "{username}" deleted successfully!')
        else:
            messages.error(request, 'Invalid confirmation text!')
            
    return redirect('manage_users')