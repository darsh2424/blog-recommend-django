# blog/management/commands/precompute_similarity.py

import os
import pandas as pd
import pickle
from django.core.management.base import BaseCommand
from blog.models import Post
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

class Command(BaseCommand):
    help = "Precompute blog post similarity matrix and save to disk (for recommendation system)"

    def handle(self, *args, **options):
        try:
            posts = Post.objects.all().values('id', 'title', 'content')
            df = pd.DataFrame(posts)

            if df.empty:
                self.stdout.write(self.style.WARNING("⚠ No posts found. Skipping similarity computation."))
                return

            if df.shape[0] < 3:
                self.stdout.write(self.style.WARNING("⚠ Too few posts (<3) to compute meaningful similarities."))
                return

            df['text'] = df['title'].fillna('') + " " + df['content'].fillna('')

            tfidf = TfidfVectorizer(stop_words='english')
            tfidf_matrix = tfidf.fit_transform(df['text'])
            cosine_sim = cosine_similarity(tfidf_matrix)

            index_map = {row['id']: idx for idx, row in df.iterrows()}

            cache_dir = 'recommend/cache'
            os.makedirs(cache_dir, exist_ok=True)

            with open(os.path.join(cache_dir, 'index_map.pkl'), 'wb') as f:
                pickle.dump(index_map, f)

            with open(os.path.join(cache_dir, 'similarity_matrix.pkl'), 'wb') as f:
                pickle.dump(cosine_sim, f)

            self.stdout.write(self.style.SUCCESS(f"✓ Precomputed similarity for {df.shape[0]} posts."))
            self.stdout.write(self.style.SUCCESS("✓ Saved to 'recommend/cache/'."))

        except Exception as e:
            self.stderr.write(self.style.ERROR(f"❌ Error during similarity precomputation: {e}"))
