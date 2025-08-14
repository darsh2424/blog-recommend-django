from django.urls import path
from . import views

urlpatterns = [
    path('', views.mis_dashboard, name='dashboard'),
    path('api/user-growth/', views.chart_user_growth, name='chart_user_growth'),
    path('api/dau/', views.chart_daily_active_users, name='chart_daily_active_users'),
    path('api/post-engagement/', views.chart_post_engagement, name='chart_post_engagement'),
    path('api/top-posts/', views.chart_top_posts, name='chart_top_posts'),
    path('api/categories/', views.chart_category_breakdown, name='chart_category_breakdown'),
    path('api/reports/', views.chart_reports, name='chart_reports'),

    path('categories/', views.manage_categories, name='manage_categories'),
    path('categories/add/', views.add_category, name='add_category'),
    path('categories/delete/<int:category_id>/', views.delete_category, name='delete_category'),
    path('posts/', views.manage_posts, name='manage_posts'),
    path('posts/delete/<int:post_id>/', views.delete_post, name='delete_post'),
    path('users/', views.manage_users, name='manage_users'),
    path('users/delete/<int:user_id>/', views.delete_user, name='delete_user'),
]
