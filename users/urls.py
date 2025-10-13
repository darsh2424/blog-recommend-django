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

    path('search/', views.search_view, name='search_view'),
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
    path('post/<int:post_id>/like/', views.toggle_like, name='toggle_like'),
    path('post/<int:post_id>/save/', views.toggle_save, name='toggle_save'),
    path("post/<int:post_id>/report/", views.report_post, name="report_post"),
    path('post/<int:post_id>/comment/', views.add_comment, name='add_comment'),
    path('comment/<int:comment_id>/reply/', views.add_reply, name='add_reply'),
    path('comment/<int:comment_id>/inline-edit/', views.inline_edit_comment, name='inline_edit_comment'),
    path('comment/<int:comment_id>/delete/', views.delete_comment, name='delete_comment'),
    path('reply/<int:reply_id>/inline-edit/', views.inline_edit_reply, name='inline_edit_reply'),
    path('reply/<int:reply_id>/delete/', views.delete_reply, name='delete_reply'),

    path('saved-posts/', views.saved_posts_view, name='saved_posts'),
    path('liked-posts/', views.liked_posts_view, name='liked_posts'),
]
