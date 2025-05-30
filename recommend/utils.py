import pickle
from datetime import timedelta
from django.db.models import F
from django.utils.timezone import now
from blog.models import Post
from users.models import UserProfile, PostInteraction
import pandas as pd

WEIGHTS = {
    'liked': 3,
    'saved': 2,
    'viewed': 1,
    'same_category_boost': 1.5
}

def get_cold_start_recommendations(user=None, top_n=5):
    recent_time = now() - timedelta(days=3)

    trending_posts = (
        Post.objects.filter(created_at__gte=recent_time)
        .annotate(score=F('views_count') + F('like_count') * 2)
        .order_by('-score')[:top_n]
    )

    if user:
        try:
            profile = user.profile
            if profile.category_preferences.exists():
                category_ids = profile.category_preferences.all().values_list('id', flat=True)
                category_posts = (
                    Post.objects
                    .filter(category_id__in=category_ids)
                    .exclude(id__in=trending_posts.values_list('id', flat=True))
                    .order_by('-created_at')[:top_n]
                )
                return list(trending_posts) + list(category_posts)
        except UserProfile.DoesNotExist:
            pass

    return trending_posts


def load_similarity_matrix():
    try:
        with open('recommend/cache/index_map.pkl', 'rb') as f:
            index_map = pickle.load(f)
        with open('recommend/cache/similarity_matrix.pkl', 'rb') as f:
            sim_matrix = pickle.load(f)
        return index_map, sim_matrix
    except FileNotFoundError:
        return {}, []



def get_user_recommendations(user, top_n=5):
    index_map, sim_matrix = load_similarity_matrix()
    interactions = PostInteraction.objects.filter(user=user)

    if not interactions.exists():
        return get_cold_start_recommendations(user, top_n)

    post_data = Post.objects.values('id', 'category_id')
    post_df = pd.DataFrame(post_data).set_index('id')

    user_categories = set(Post.objects.filter(user=user).values_list('category_id', flat=True))

    weighted_scores = {}

    for interaction in interactions:
        try:
            blog_index = index_map[interaction.post.id]
        except KeyError:
            continue

        weight = 0
        if interaction.liked: weight += WEIGHTS['liked']
        if interaction.saved: weight += WEIGHTS['saved']
        if interaction.viewed: weight += WEIGHTS['viewed']
        if weight == 0: continue

        similarity_scores = sim_matrix[blog_index]
        for idx, score in enumerate(similarity_scores):
            target_post_id = list(index_map.keys())[list(index_map.values()).index(idx)]
            if target_post_id == interaction.post.id:
                continue  # skip self

            post_category = post_df.loc[target_post_id]['category_id']
            boost = WEIGHTS['same_category_boost'] if post_category in user_categories else 1

            weighted_scores[target_post_id] = weighted_scores.get(target_post_id, 0) + score * weight * boost

    if not weighted_scores:
        return get_cold_start_recommendations(user, top_n)

    top_ids = sorted(weighted_scores, key=weighted_scores.get, reverse=True)[:top_n]
    return Post.objects.filter(id__in=top_ids)


def similar_posts_for_post(post_id, top_n=5):
    index_map, sim_matrix = load_similarity_matrix()
    try:
        idx = index_map[post_id]
    except KeyError:
        return []

    similar_indices = sim_matrix[idx].argsort()[::-1][1:top_n + 1]
    similar_ids = [list(index_map.keys())[i] for i in similar_indices]
    return Post.objects.filter(id__in=similar_ids)


def get_trending_posts_by_score(category=None, days=7, top_n=None):
    today = now().date()
    start_date = today - timedelta(days=days)

    queryset = Post.objects.filter(created_at__date__range=(start_date, today))
    if category:
        queryset = queryset.filter(category=category)

    post_scores = []
    for post in queryset:
        days_old = max((today - post.created_at.date()).days, 1)
        score = (post.views_count + post.like_count * 2 + post.comment_count * 1.5) / days_old
        post_scores.append((score, post))

    sorted_posts = sorted(post_scores, key=lambda x: x[0], reverse=True)
    final_posts = [p[1] for p in sorted_posts]

    return final_posts[:top_n] if top_n else final_posts
