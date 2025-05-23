from django.urls import path
from . import views
from .views import logout_view

urlpatterns = [
    path('', views.index),
    path('profile_dtl/', views.profile_dtl, name='profile_dtl'),
    path('other_dtl/', views.other_dtl, name='other_dtl'),
    path('logout/', logout_view, name='logout'),
]
