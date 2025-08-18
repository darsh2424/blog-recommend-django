from datetime import timedelta
from django.db import models  
import time
from django.utils.timezone import now
from django.db.models import Count, Q, F, ExpressionWrapper, FloatField
from django.core.cache import cache
from django.conf import settings
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from blog.models import Post, Category
from users.models import PostInteraction, UserProfile, User
import pickle
import pandas as pd
from random import sample
from collections import defaultdict
import os
# Constants

USER_RECS_CACHE_TIMEOUT = 10 * 60 
SIMILARITY_CACHE_TIMEOUT = 30 * 60 
COLD_START_DAYS = 3 

WEIGHTS = {
    'view': 1,
    'like': 2, 
    'comment': 1.5,
    'same_category_boost': 1.3
}
def get_trending_posts(category=None, days=7, top_n=10, require_interactions=False):
    posts = _calculate_trending_posts(category, days, top_n) 
    return posts

def _calculate_trending_posts(category=None, days=7, top_n=10, require_interactions=False):
    """Improved with better fallbacks"""
    qs = Post.objects.all()
    
    if days:
        time_filter = now() - timedelta(days=days)
        qs = qs.filter(created_at__gte=time_filter)
    
    if category:
        qs = qs.filter(category=category)
    
    # Only annotate scores if we have interactions
    qs = qs.annotate(
        num_views=Count('interactions', filter=Q(interactions__viewed=True)),
        num_likes=Count('interactions', filter=Q(interactions__liked=True)),
        num_comments=Count('comments'),
        hours_since_post=ExpressionWrapper(
            (now() - F('created_at')) / timedelta(hours=1),
            output_field=FloatField()
        ),
        score=ExpressionWrapper(
            (
                (F('num_views') * WEIGHTS['view']) +
                (F('num_likes') * WEIGHTS['like']) +
                (F('num_comments') * WEIGHTS['comment'])
            ) / (1 + F('hours_since_post')/24),  # Recent posts get boost
            output_field=FloatField()
        )
    ).order_by('-score', '-created_at')
    
    return qs[:top_n]

def get_user_recommendations(user, top_n=10):
    sim_matrix, index_map = load_similarity_data()
    liked_post_ids = set()
    weighted_scores = defaultdict(float)

    # Step 1: Content-based filtering via similarity
    interactions = PostInteraction.objects.filter(user=user, liked=True).select_related('post')
    
    for interaction in interactions:
        try:
            liked_post_ids.add(interaction.post.id)
            idx = index_map[interaction.post.id]
            similar_indices = sim_matrix[idx].argsort()[::-1][1:30]
            for i in similar_indices:
                pid = list(index_map.keys())[i]
                if pid != interaction.post.id:
                    weighted_scores[pid] += sim_matrix[idx][i]
        except Exception:
            continue

    # Remove already liked
    for pid in liked_post_ids:
        weighted_scores.pop(pid, None)

    top_similar_ids = sorted(weighted_scores, key=weighted_scores.get, reverse=True)[:top_n*2]

    # Step 2: Trending
    trending_ids = list(Post.objects.annotate(
        likes=Count('interactions', filter=Q(interactions__liked=True)),
        views=Count('interactions', filter=Q(interactions__viewed=True))
    ).order_by('-likes', '-views', '-created_at').values_list('id', flat=True)[:top_n*2])

    # Step 3: Recent
    recent_ids = list(Post.objects.order_by('-created_at').values_list('id', flat=True)[:top_n*2])

    # Step 4: Profile Category Preference
    category_pref_ids = []
    if hasattr(user, 'profile') and user.profile.category_preferences.exists():
        category_pref_ids = list(
            Post.objects.filter(category__in=user.profile.category_preferences.all())
            .order_by('-created_at')
            .exclude(id__in=top_similar_ids + trending_ids + recent_ids)
            .values_list('id', flat=True)[:top_n*2]
        )

    # Step 5: Merge with diversity enforcement
    combined = []
    seen = set()
    cat_count = defaultdict(int)
    MAX_PER_CATEGORY = 3

    def add_unique(ids):
        for pid in ids:
            if pid not in seen:
                category_id = Post.objects.filter(id=pid).values_list('category_id', flat=True).first()
                if cat_count[category_id] >= MAX_PER_CATEGORY:
                    continue
                combined.append(pid)
                seen.add(pid)
                cat_count[category_id] += 1
            if len(combined) >= top_n:
                break

    add_unique(top_similar_ids)
    add_unique(trending_ids)
    add_unique(recent_ids)
    add_unique(category_pref_ids)

    # Step 6: Cold-start fallback (exploration)
    if len(combined) < top_n:
        fallback_ids = list(
            Post.objects.exclude(id__in=seen).order_by('?').values_list('id', flat=True)[:top_n]
        )
        add_unique(fallback_ids)

    return Post.objects.filter(id__in=combined).select_related('user', 'category')


def similar_posts_for_post(post_id, top_n=5):
    """Get similar posts using precomputed similarity matrix"""
    sim_matrix, index_map = load_similarity_data()
    if not sim_matrix:
        return []

    try:
        idx = index_map[post_id]
        similar_indices = sim_matrix[idx].argsort()[::-1][1:top_n + 1]
        similar_ids = [list(index_map.keys())[i] for i in similar_indices]
        return list(Post.objects.filter(id__in=similar_ids))
    except KeyError:
        return []

def load_similarity_data():
    cache_key = "similarity_data"
    if cached := cache.get(cache_key):
        return cached

    try:
        cache_dir = os.path.join(settings.BASE_DIR, 'recommend/cache')
        with open(os.path.join(cache_dir, 'similarity_matrix.pkl'), 'rb') as f:
            sim_matrix = pickle.load(f)
        with open(os.path.join(cache_dir, 'index_map.pkl'), 'rb') as f:
            index_map = pickle.load(f)

        cache.set(cache_key, (sim_matrix, index_map), 3600)
        return sim_matrix, index_map
    except Exception as e:
        print(f"Similarity load error: {str(e)}")
        return None, None