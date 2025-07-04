from django.urls import path
from . import views
from .views import logout_view

urlpatterns = [
    path('', views.index,name='index'),
    path('trending/<slug:category_slug>/', views.trending_category_view, name='trending_category'),

    path('profile_dtl/', views.profile_dtl, name='profile_dtl'),
    path('other_dtl/', views.other_dtl, name='other_dtl'),
    path('select-interests/', views.interest_selection_view, name='interest_selection'),
    path('logout/', logout_view, name='logout'),

    path('for-you/', views.for_you_view, name='for_you'),
    path('user/<str:username>/follow/', views.follow_unfollow_user, name='follow_user'),
    path('following/', views.following_posts, name='following_posts'),
    # path('category/<slug:category_slug>/', views.category_view, name='category_view'),
    # path('trending/', views.trending_view, name='trending'),
    # path('trending/<slug:category_slug>/', views.trending_view, name='trending_category'),

    path('post/<int:post_id>/', views.post_detail_view, name='post_detail'),
    path('profile/<str:username>/', views.user_profile_view, name='user_profile'),
    path('post/<int:post_id>/edit/', views.edit_post_view, name='edit_post'),
    path('post/<int:post_id>/delete/', views.delete_post_view, name='delete_post'),

    path('write/', views.write_post_view, name='write_post'),
]
