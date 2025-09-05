import os
import pandas as pd
import pickle
from django.core.cache import cache
from django.conf import settings
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from datetime import timedelta
from django.utils.timezone import now
from blog.models import Post
def calculate_similarity(force_update=False):
    """Optimized similarity calculation with caching"""
    cache_key = "similarity_data"
    last_updated_key = "similarity_last_updated"
    
    # Check if we can use cached version
    if not force_update:
        last_updated = cache.get(last_updated_key)
        if last_updated and (now() - last_updated) < timedelta(hours=12):
            return cache.get(cache_key)
    
    try:
        # Only get recent posts with interactions
        recent_posts = Post.objects.filter(
            created_at__gte=now()-timedelta(days=60)
        ).exclude(interactions__isnull=True).distinct()
        
        if recent_posts.count() < 3:
            return None
        
        # Prepare data efficiently
        post_data = []
        for post in recent_posts.only('id', 'title', 'content'):
            post_data.append({
                'id': post.id,
                'text': f"{post.title or ''} {post.content or ''}"
            })
        
        df = pd.DataFrame(post_data)
        tfidf = TfidfVectorizer(stop_words='english', max_features=5000)
        tfidf_matrix = tfidf.fit_transform(df['text'])
        cosine_sim = cosine_similarity(tfidf_matrix)
        
        index_map = {row['id']: idx for idx, row in df.iterrows()}
        
        # Cache the results
        result = (cosine_sim, index_map)
        cache.set(cache_key, result, 86400)  # 24 hours
        cache.set(last_updated_key, now(), 86400)
        
        # Save to disk as backup
        cache_dir = os.path.join(settings.BASE_DIR, 'recommend/cache')
        os.makedirs(cache_dir, exist_ok=True)
        
        with open(os.path.join(cache_dir, 'index_map.pkl'), 'wb') as f:
            pickle.dump(index_map, f)
        
        with open(os.path.join(cache_dir, 'similarity_matrix.pkl'), 'wb') as f:
            pickle.dump(cosine_sim, f)
        
        return result
        
    except Exception as e:
        print(f"Similarity calculation error: {str(e)}")
        return None
