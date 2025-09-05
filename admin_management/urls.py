from django.urls import path
from . import views

urlpatterns = [
    path('login/', views.admin_login, name='admin_login'),
    path('logout/', views.admin_logout, name='admin_logout'),
    path('', views.admin_dashboard, name='dashboard'),
    path('api/chart-data/', views.get_chart_data, name='get_chart_data'),
    path('api/dashboard-stats/', views.get_dashboard_stats, name='get_dashboard_stats'),
    path('categories/', views.manage_categories, name='manage_categories'),
    path('categories/add/', views.add_category, name='add_category'),
    path('categories/delete/<int:category_id>/', views.delete_category, name='delete_category'),
    path('posts/', views.manage_posts, name='manage_posts'),
    path('posts/suspend/<int:post_id>/', views.suspend_post, name='suspend_post'),
    path('users/', views.manage_users, name='manage_users'),
    path('users/suspend/<int:user_id>/', views.suspend_user, name='suspend_user'),
]
