import logging
from django.core.management.base import BaseCommand
from blog.models import Post, Category
from django.utils.timezone import now
from datetime import timedelta
from django.core.cache import cache

class Command(BaseCommand):
    help = "Precompute and cache category-wise trending blogs for weekly trending view"

    def handle(self, *args, **kwargs):
        try:
            today = now().date()
            week_ago = today - timedelta(days=7)

            recent_posts = Post.objects.filter(created_at__date__range=(week_ago, today))

            category_scores = {}
            category_posts = {}

            for post in recent_posts:
                days_old = max((today - post.created_at.date()).days, 1)
                score = post.views_count / days_old

                if post.category_id not in category_scores:
                    category_scores[post.category_id] = []
                    category_posts[post.category_id] = []

                category_scores[post.category_id].append(score)
                category_posts[post.category_id].append((score, post))

            category_avg = []
            for cat_id, scores in category_scores.items():
                avg_score = sum(scores) / len(scores)
                cat = Category.objects.get(id=cat_id)
                category_avg.append((avg_score, cat))

            sorted_categories = sorted(category_avg, key=lambda x: x[0], reverse=True)

            category_post_map = []
            for _, cat in sorted_categories:
                posts = category_posts.get(cat.id, [])
                top_3 = sorted(posts, key=lambda x: x[0], reverse=True)[:3]
                top_posts = [p[1] for p in top_3]
                category_post_map.append((cat, top_posts))

            # Cache the result for 6 hours
            cache.set('trending_category_map', category_post_map, timeout=21600)

            self.stdout.write(self.style.SUCCESS("✅ Trending category map cached successfully."))
            self.stdout.write(self.style.SUCCESS(f"✅ Total categories: {len(category_post_map)}"))

        except Exception as e:
            self.stderr.write(self.style.ERROR(f"❌ Failed to cache trending category map: {e}"))
