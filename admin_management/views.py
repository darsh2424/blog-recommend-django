from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth import authenticate, login, logout
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
from django.core.paginator import Paginator
from functools import wraps

def is_admin(user):
    """Check if user is staff/admin"""
    return user.is_authenticated and (user.is_staff or user.is_superuser)

def admin_required(view_func):
    """Custom decorator that redirects to admin login if user is not admin"""
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('admin_login')
        if not is_admin(request.user):
            messages.error(request, 'You do not have permission to access this area.')
            return redirect('admin_login')
        return view_func(request, *args, **kwargs)
    return _wrapped_view

def admin_login(request):
    """Admin login view"""
    if request.user.is_authenticated and is_admin(request.user):
        return redirect('dashboard')
    
    if request.method == 'POST':
        email = request.POST.get('email') 
        password = request.POST.get('password')
        
        if email and password:
           
            user = authenticate(request, username=email, password=password)
            if user is not None and is_admin(user):
                login(request, user)
                messages.success(request, f'Welcome back, {user.username or user.email}!')
                return redirect('dashboard')
            else:
                if user is None:
                    messages.error(request, 'Invalid email or password.')
                else:
                    messages.error(request, 'You do not have admin privileges to access this area.')
        else:
            messages.error(request, 'Please provide both email and password.')
    
    return render(request, 'admin_management/login.html')

@admin_required
def admin_logout(request):
    """Admin logout view"""
    logout(request)
    messages.success(request, 'Successfully logged out!')
    return redirect('admin_login')

@admin_required
def admin_dashboard(request):
    """MIS Dashboard with dynamic charts"""
    return render(request, 'admin_management/dashboard.html', {'active_section': 'dashboard'})

@admin_required
def get_chart_data(request):
    """API endpoint for chart data based on date range"""
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    chart_type = request.GET.get('chart_type')

    # Default to last 7 days if no dates provided
    if not start_date or not end_date:
        end_date = timezone.now().date()
        start_date = end_date - timedelta(days=7)
    else:
        start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
        end_date = datetime.strptime(end_date, '%Y-%m-%d').date()

    # Calculate the date range
    date_range = (end_date - start_date).days

    # Determine grouping based on date range
    if date_range <= 15:
        # Daily grouping
        group_by = 'day'
        date_format = '%Y-%m-%d'
        label_format = '%m/%d'
    elif date_range <= 150:
        # Weekly grouping
        group_by = 'week'
        date_format = '%Y-W%U'
        label_format = 'Week %U'
    else:
        # Monthly grouping
        group_by = 'month'
        date_format = '%Y-%m'
        label_format = '%b %Y'

    data = {}

    if chart_type == 'user_growth':
        data = get_user_growth_data(start_date, end_date, group_by, label_format)
    elif chart_type == 'daily_active_users':
        data = get_daily_active_users_data(start_date, end_date, group_by, label_format)
    elif chart_type == 'post_engagement':
        data = get_post_engagement_data(start_date, end_date, group_by, label_format)
    elif chart_type == 'top_posts':
        data = get_top_posts_data(start_date, end_date)
    elif chart_type == 'category_breakdown':
        data = get_category_breakdown_data(start_date, end_date)
    elif chart_type == 'reports':
        data = get_reports_data(start_date, end_date, group_by, label_format)

    return JsonResponse(data)

def get_user_growth_data(start_date, end_date, group_by, label_format):
    """Get user growth data"""
    labels = []
    new_users = []
    current_date = start_date

    while current_date <= end_date:
        if group_by == 'day':
            next_date = current_date + timedelta(days=1)
            label = current_date.strftime('%m/%d')
        elif group_by == 'week':
            next_date = current_date + timedelta(days=7)
            label = f"Week {current_date.strftime('%U')}"
        else:
            next_date = (current_date.replace(day=28) + timedelta(days=4)).replace(day=1)
            label = current_date.strftime('%b %Y')

        # Fixed: Added proper underscores for Django ORM lookup
        user_count = User.objects.filter(
            created_at__date__gte=current_date,
            created_at__date__lt=next_date
        ).count()

        labels.append(label)
        new_users.append(user_count)
        current_date = next_date

    return {
        'labels': labels,
        'datasets': [{
            'label': 'New Users',
            'data': new_users,
            'borderColor': 'rgb(59, 130, 246)',
            'backgroundColor': 'rgba(59, 130, 246, 0.1)',
            'tension': 0.1
        }]
    }

def get_daily_active_users_data(start_date, end_date, group_by, label_format):
    """Get daily active users data"""
    labels = []
    active_users = []
    current_date = start_date

    while current_date <= end_date:
        if group_by == 'day':
            next_date = current_date + timedelta(days=1)
            label = current_date.strftime('%m/%d')
        elif group_by == 'week':
            next_date = current_date + timedelta(days=7)
            label = f"Week {current_date.strftime('%U')}"
        else:
            next_date = (current_date.replace(day=28) + timedelta(days=4)).replace(day=1)
            label = current_date.strftime('%b %Y')

        # Fixed: Added proper underscores for Django ORM lookup
        active_count = PostInteraction.objects.filter(
            timestamp__date__gte=current_date,
            timestamp__date__lt=next_date
        ).values('user').distinct().count()

        labels.append(label)
        active_users.append(active_count)
        current_date = next_date

    return {
        'labels': labels,
        'datasets': [{
            'label': 'Active Users',
            'data': active_users,
            'borderColor': 'rgb(34, 197, 94)',
            'backgroundColor': 'rgba(34, 197, 94, 0.1)',
            'tension': 0.1
        }]
    }

def get_post_engagement_data(start_date, end_date, group_by, label_format):
    """Get post engagement data"""
    labels = []
    posts_data = []
    likes_data = []
    views_data = []
    current_date = start_date

    while current_date <= end_date:
        if group_by == 'day':
            next_date = current_date + timedelta(days=1)
            label = current_date.strftime('%m/%d')
        elif group_by == 'week':
            next_date = current_date + timedelta(days=7)
            label = f"Week {current_date.strftime('%U')}"
        else:
            next_date = (current_date.replace(day=28) + timedelta(days=4)).replace(day=1)
            label = current_date.strftime('%b %Y')

        # Fixed: Added proper underscores for Django ORM lookup
        posts_count = Post.objects.filter(
            created_at__date__gte=current_date,
            created_at__date__lt=next_date
        ).count()

        likes_count = PostInteraction.objects.filter(
            liked=True,
            timestamp__date__gte=current_date,
            timestamp__date__lt=next_date
        ).count()

        views_count = PostInteraction.objects.filter(
            viewed=True,
            timestamp__date__gte=current_date,
            timestamp__date__lt=next_date
        ).count()

        labels.append(label)
        posts_data.append(posts_count)
        likes_data.append(likes_count)
        views_data.append(views_count)
        current_date = next_date

    return {
        'labels': labels,
        'datasets': [{
            'label': 'Posts',
            'data': posts_data,
            'backgroundColor': 'rgba(59, 130, 246, 0.8)'
        }, {
            'label': 'Likes',
            'data': likes_data,
            'backgroundColor': 'rgba(239, 68, 68, 0.8)'
        }, {
            'label': 'Views',
            'data': views_data,
            'backgroundColor': 'rgba(34, 197, 94, 0.8)'
        }]
    }

def get_top_posts_data(start_date, end_date):
    top_posts = Post.objects.filter(
        created_at__date__gte=start_date,
        created_at__date__lte=end_date
    ).annotate(
        annotated_likes=Count('interactions', filter=Q(interactions__liked=True)),
        annotated_views=Count('interactions', filter=Q(interactions__viewed=True))
    ).order_by('-annotated_likes')[:7]

    labels = [post.title[:30] + '...' if len(post.title) > 30 else post.title for post in top_posts]
    likes_data = [post.annotated_likes for post in top_posts]
    views_data = [post.annotated_views for post in top_posts]

    return {
        'labels': labels,
        'datasets': [{
            'label': 'Likes',
            'data': likes_data,
            'backgroundColor': 'rgba(239, 68, 68, 0.8)'
        }, {
            'label': 'Views',
            'data': views_data,
            'backgroundColor': 'rgba(34, 197, 94, 0.8)'
        }]
    }
    
def get_category_breakdown_data(start_date, end_date):
    """Get category breakdown data"""
    # Fixed: Added proper underscores for Django ORM lookup
    categories = Category.objects.annotate(
        posts_count=Count('posts', filter=Q(
            posts__created_at__date__gte=start_date,
            posts__created_at__date__lte=end_date
        ))
    ).filter(posts_count__gt=0).order_by('-posts_count')

    labels = [cat.name for cat in categories]
    data = [cat.posts_count for cat in categories]

    # Generate colors
    colors = [
        '#8884d8', '#82ca9d', '#ffc658', '#ff7c7c', '#8dd1e1',
        '#d084d0', '#87ceeb', '#dda0dd', '#98fb98', '#f0e68c'
    ]

    return {
        'labels': labels,
        'datasets': [{
            'data': data,
            'backgroundColor': colors[:len(labels)]
        }]
    }

def get_reports_data(start_date, end_date, group_by, label_format):
    """Get reports data"""
    labels = []
    reports_data = []
    current_date = start_date

    while current_date <= end_date:
        if group_by == 'day':
            next_date = current_date + timedelta(days=1)
            label = current_date.strftime('%m/%d')
        elif group_by == 'week':
            next_date = current_date + timedelta(days=7)
            label = f"Week {current_date.strftime('%U')}"
        else:
            next_date = (current_date.replace(day=28) + timedelta(days=4)).replace(day=1)
            label = current_date.strftime('%b %Y')

        # Fixed: Added proper underscores for Django ORM lookup
        reports_count = PostReport.objects.filter(
            reported_at__date__gte=current_date,
            reported_at__date__lt=next_date
        ).count()

        labels.append(label)
        reports_data.append(reports_count)
        current_date = next_date

    return {
        'labels': labels,
        'datasets': [{
            'label': 'Reports',
            'data': reports_data,
            'backgroundColor': 'rgba(239, 68, 68, 0.8)',
            'borderColor': 'rgb(239, 68, 68)',
            'tension': 0.1
        }]
    }

@admin_required
def get_dashboard_stats(request):
    """Get dashboard statistics"""
    stats = {
        'total_users': User.objects.count(),
        'total_posts': Post.objects.count(),
        'total_categories': Category.objects.count(),
        'total_reports': PostReport.objects.count(),
    }
    
    return JsonResponse(stats)

@admin_required
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

@admin_required
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

@admin_required
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

@admin_required
def manage_posts(request):
    """Manage Posts with all counters, reports, search and filters"""
    # Get all posts with annotations
    posts = Post.objects.select_related('user', 'category').annotate(
        annotated_likes_count=Count('interactions', filter=Q(interactions__liked=True)),
        annotated_views_count=Count('interactions', filter=Q(interactions__viewed=True)),
        annotated_comments_count=Count('comments'),
        annotated_reports_count=Count('admin_reports')
    )
    
    # Search functionality
    search_query = request.GET.get('search', '')
    if search_query:
        posts = posts.filter(
            Q(title__icontains=search_query) |
            Q(content__icontains=search_query) |
            Q(user__username__icontains=search_query) |
            Q(category__name__icontains=search_query)
        )
    
    # Filtering
    filter_type = request.GET.get('filter', '')
    if filter_type:
        if filter_type == 'most_reported':
            posts = posts.order_by('-annotated_reports_count')
        elif filter_type == 'most_liked':
            posts = posts.order_by('-annotated_likes_count')
        elif filter_type == 'most_viewed':
            posts = posts.order_by('-annotated_views_count')
        elif filter_type == 'most_commented':
            posts = posts.order_by('-annotated_comments_count')
        elif filter_type == 'recent':
            posts = posts.order_by('-created_at')
        elif filter_type == 'oldest':
            posts = posts.order_by('created_at')
    else:
        posts = posts.order_by('-created_at')  # Default sorting
    
    # Get report details for tooltips
    post_reports = {}
    for post in posts:
        if post.annotated_reports_count > 0:
            reports = PostReport.objects.filter(post=post).values('reason').annotate(
                count=Count('reason')
            ).order_by('-count')
            post_reports[post.id] = list(reports)
    # print(post_reports)
    
    # Pagination
    paginator = Paginator(posts, 25)  # Show 25 posts per page
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'posts': page_obj,
        'post_reports': post_reports,
        'active_section': 'posts',
        'search_query': search_query,
        'current_filter': filter_type,
    }
    return render(request, 'admin_management/manage_posts.html', context)

@admin_required
def suspend_post(request, post_id):
    """Suspend post instead of deleting (with confirmation)"""
    if request.method == 'POST':
        confirmation_text = request.POST.get('confirmation_text', '')
        expected_text = f"Suspend Post {post_id}"
        
        if confirmation_text == expected_text:
            post = get_object_or_404(Post, id=post_id)
            post_title = post.title

            # Instead of deleting → mark as suspended
            post.is_suspended = True
            post.status = 'suspended'
            post.save()  # 🔥 signals will log automatically

            messages.success(request, f'Post "{post_title}" suspended successfully!')
        else:
            messages.error(request, 'Invalid confirmation text!')
            
    return redirect('manage_posts')


@admin_required
def manage_users(request):
    """Manage Users with all counters, reports, search and filters"""
    # Get all users with annotations
    users = User.objects.select_related('profile').annotate(
        total_posts=Count('posts'),
        total_likes=Count('posts__interactions', filter=Q(posts__interactions__liked=True)),
        total_views=Count('posts__interactions', filter=Q(posts__interactions__viewed=True)),
        total_comments=Count('posts__comments'),
        reports_count=Count('posts__admin_reports'),
        unique_reports_count=Count('posts__admin_reports__reason', distinct=True)
    )
    
    # Search functionality
    search_query = request.GET.get('search', '')
    if search_query:
        users = users.filter(
            Q(username__icontains=search_query) |
            Q(email__icontains=search_query) |
            Q(profile__full_name__icontains=search_query)
        )
    
    # Filtering
    filter_type = request.GET.get('filter', '')
    if filter_type:
        if filter_type == 'most_active':
            users = users.order_by('-total_posts')
        elif filter_type == 'most_reported':
            users = users.order_by('-reports_count')
        elif filter_type == 'most_liked':
            users = users.order_by('-total_likes')
        elif filter_type == 'most_viewed':
            users = users.order_by('-total_views')
        elif filter_type == 'most_commented':
            users = users.order_by('-total_comments')
        elif filter_type == 'newest':
            users = users.order_by('-created_at')
        elif filter_type == 'oldest':
            users = users.order_by('created_at')
    else:
        users = users.order_by('-total_posts')  # Default sorting
    
    # Get report details for tooltips
    user_reports = {}
    for user in users:
        if user.reports_count > 0:
            reports = PostReport.objects.filter(post__user=user).values('reason').annotate(
                count=Count('reason')
            ).order_by('-count')
            user_reports[user.id] = list(reports)

    # Pagination
    paginator = Paginator(users, 25)  # Show 25 users per page
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'users': page_obj,
        'user_reports': user_reports,
        'active_section': 'users',
        'search_query': search_query,
        'current_filter': filter_type,
    }
    return render(request, 'admin_management/manage_users.html', context)

@admin_required
def suspend_user(request, user_id):
    """Suspend user instead of deleting (with confirmation)"""
    if request.method == 'POST':
        confirmation_text = request.POST.get('confirmation_text', '')
        expected_text = f"Suspend User {user_id}"
        
        if confirmation_text == expected_text:
            user = get_object_or_404(User, id=user_id)
            username = user.username or user.email

            user.is_suspended = True
            user.status = 'suspended'
            user.save()  

            messages.success(request, f'User "{username}" suspended successfully!')
        else:
            messages.error(request, 'Invalid confirmation text!')
            
    return redirect('manage_users')