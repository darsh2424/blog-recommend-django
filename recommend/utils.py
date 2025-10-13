from datetime import timedelta
from django.db import models  
import time
from django.utils import timezone
from django.utils.timezone import now
from django.db.models import Count, Q, F, ExpressionWrapper, FloatField
from django.core.cache import cache
from django.conf import settings
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from blog.models import Post, Category, RecommendationLog
from users.models import PostInteraction, UserProfile, User
import pickle
import pandas as pd
import random
from random import sample
from collections import defaultdict
import os
import numpy as np
from django.db.models.functions import Now
from django.db.models import (
    Q, F, Count, Case, When, FloatField, ExpressionWrapper, Value
)


WEIGHTS = {
    'view': 1,
    'like': 2, 
    'comment': 1.5
}

ENGAGED_WEIGHT = 3
FRESH_WEIGHT = 2
TRENDING_WEIGHT = 1

MAX_RECOMMENDATIONS = 10
MAX_PER_CATEGORY = 3

def get_trending_posts(category=None, days=7, top_n=10, require_interactions=False):
    posts = _calculate_trending_posts(category, days, top_n) 
    return posts

def _calculate_trending_posts(category=None, days=7, top_n=10, require_interactions=False):
    """Improved with better fallbacks"""
    qs = Post.objects.filter(is_suspended=False)
    
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
            ) / (1 + F('hours_since_post')/24),  
            output_field=FloatField()
        )
    ).order_by('-score', '-created_at')
    
    return qs[:top_n]

def get_user_recommendations(user, top_n=10, repeat_after_hours=12):

    sim_matrix, index_map = load_similarity_data()
    if sim_matrix is None or index_map is None:
        sim_matrix, index_map = None, {}

    weighted_scores = defaultdict(float)
    liked_post_ids = set()

    # === Exclude posts already shown recently (unless engaged) ===
    cutoff_time = timezone.now() - timedelta(hours=repeat_after_hours)
    already_seen_ids = set(
        RecommendationLog.objects.filter(
            user=user,
            created_at__gte=cutoff_time,   
            clicked=False,
            engaged=False
        ).values_list("post_id", flat=True)
    )

    # --- Step 1: Feedback loop (Similarity-based CTR boost) ---
    interactions = PostInteraction.objects.filter(user=user, liked=True).select_related("post")
    for interaction in interactions:
        liked_post_ids.add(interaction.post.id)
        if sim_matrix is not None and interaction.post.id in index_map:
            idx = index_map[interaction.post.id]
            similar_indices = sim_matrix[idx].argsort()[::-1][1:30]
            for i in similar_indices:
                pid = list(index_map.keys())[i]
                if pid != interaction.post.id:
                    weighted_scores[pid] += float(sim_matrix[idx][i])

    # remove already liked
    for pid in liked_post_ids:
        weighted_scores.pop(pid, None)

    top_similar_ids = [
        pid for pid in sorted(weighted_scores, key=weighted_scores.get, reverse=True)
        if pid not in already_seen_ids
    ][: top_n * 2]

    # --- Step 2: Trending (popularity boost) ---
    trending_ids = list(
        Post.objects.filter(is_suspended=False)
        .exclude(id__in=already_seen_ids)
        .annotate(
            likes=Count("interactions", filter=Q(interactions__liked=True)),
            views=Count("interactions", filter=Q(interactions__viewed=True)),
        )
        .order_by("-likes", "-views", "-created_at")
        .values_list("id", flat=True)[: top_n * 2]
    )

    # --- Step 3: Freshness (new content boost) ---
    recent_ids = list(
        Post.objects.filter(is_suspended=False)
        .exclude(id__in=already_seen_ids)
        .order_by("-created_at")
        .values_list("id", flat=True)[: top_n * 2]
    )

    # --- Step 4: Profile category preference ---
    category_pref_ids = list(
        Post.objects.filter(category__in=user.profile.category_preferences.all(), is_suspended=False)
        .exclude(id__in=already_seen_ids.union(set(top_similar_ids + trending_ids + recent_ids)))
        .order_by("-created_at")
        .values_list("id", flat=True)[: top_n * 2]
    )

    # --- Step 5: Fallback cold start (exploration) ---
    fallback_ids = list(
        Post.objects.filter(is_suspended=False)
        .exclude(id__in=already_seen_ids.union(set(top_similar_ids + trending_ids + recent_ids + category_pref_ids)))
        .order_by("?")
        .values_list("id", flat=True)[: top_n]
    )

    # --- Tiered blending with weights ---
    tier_3 = list(top_similar_ids)  # Engaged/Similarity
    tier_2 = list(set(trending_ids + recent_ids))  # Trending + Fresh
    tier_1 = list(set(category_pref_ids + fallback_ids))  # Exploration

    random.shuffle(tier_3)
    random.shuffle(tier_2)
    random.shuffle(tier_1)

    combined = []
    tier_plan = [(tier_3, 3), (tier_2, 2), (tier_1, 1)]
    seen = set()

    for tier_posts, weight in tier_plan:
        for pid in tier_posts:
            if pid not in seen:
                combined.append((pid, weight))  # store with weight
                seen.add(pid)
            if len(combined) >= top_n:
                break
        if len(combined) >= top_n:
            break

    # --- Fetch actual posts ---
    post_ids = [pid for pid, _ in combined]
    posts = list(
        Post.objects.filter(id__in=post_ids, is_suspended=False)
        .select_related("user", "category")
    )

    # --- Log into RecommendationLog with tier ---
    weight_map = {pid: weight for pid, weight in combined}
    for post in posts:
        RecommendationLog.objects.create(
            user=user,
            post=post,
            tier=weight_map.get(post.id, 1),
        )

    return posts

def similar_posts_for_post(post_id, top_n=5):
    """Get similar posts using precomputed similarity matrix"""
    sim_matrix, index_map = load_similarity_data()
    if sim_matrix is None or index_map is None:
        return []

    try:
        idx = index_map[post_id]
        similar_indices = sim_matrix[idx].argsort()[::-1][1:top_n + 1]
        similar_ids = [list(index_map.keys())[i] for i in similar_indices]
        return list(Post.objects.filter(id__in=similar_ids, is_suspended=False))
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

        # ✅ make sure sim_matrix is numpy array
        sim_matrix = np.array(sim_matrix)
        cache.set(cache_key, (sim_matrix, index_map), 3600)
        return sim_matrix, index_map

    except Exception as e:
        print(f"⚠️ Similarity load error: {e}")
        return None, None
    

def search_relevant_posts(search_text, top_n=15):
    """
    Search posts based on title/content relevance,
    while promoting fresh & engaging (popular) posts.
    """

    qs = Post.objects.filter(is_suspended=False)

    # ✅ Step 1: Text relevance (basic fuzzy match)
    qs = qs.filter(
        Q(title__icontains=search_text) |
        Q(content__icontains=search_text)
    )

    # ✅ Step 2: Annotate popularity metrics
    qs = qs.annotate(
        num_likes=Count("interactions", filter=Q(interactions__liked=True)),
        num_views=Count("interactions", filter=Q(interactions__viewed=True)),
        num_comments=Count("comments"),
    )

    # ✅ Step 3: Compute popularity score (normalized)
    qs = qs.annotate(
        popularity_score=ExpressionWrapper(
            (F("num_likes") * 2) + (F("num_comments") * 1.5) + (F("num_views") * 1.0),
            output_field=FloatField()
        )
    )

    # ✅ Step 4: Freshness factor (recent posts get higher score)
    qs = qs.annotate(
        hours_since_post=ExpressionWrapper(
            (Now() - F("created_at")) / timedelta(hours=1),
            output_field=FloatField(),
        ),
        freshness_score=ExpressionWrapper(
            1 / (1 + (F("hours_since_post") / 24.0)),  # decay with age
            output_field=FloatField(),
        ),
    )

    # ✅ Step 5: Basic text relevance (approximation)
    qs = qs.annotate(
        relevance=Case(
            When(title__icontains=search_text, then=Value(1.0)),
            When(content__icontains=search_text, then=Value(0.8)),
            default=Value(0.3),
            output_field=FloatField(),
        )
    )

    # ✅ Step 6: Extra boost for *very new* posts (last 48 hours)
    recent_boost = Case(
        When(created_at__gte=Now() - timedelta(days=2), then=Value(1.3)),  # +30% boost
        default=Value(1.0),
        output_field=FloatField(),
    )

    # ✅ Step 7: Combine all into a final score
    qs = qs.annotate(
        final_score=ExpressionWrapper(
            (
                (F("relevance") * 0.6) +
                (F("popularity_score") * 0.3) +
                (F("freshness_score") * 0.1)
            ) * recent_boost,
            output_field=FloatField(),
        )
    ).order_by("-final_score", "-created_at")

    return qs[:top_n]