import logging
from django.core.management.base import BaseCommand
from django.utils.timezone import now
from datetime import timedelta
from django.core.cache import cache
from django.db.models import Count, Q, F
from blog.models import Post, Category

class Command(BaseCommand):
    help = "Precompute and cache category-wise trending blogs for weekly trending view"

    def handle(self, *args, **kwargs):
        try:
            today = now().date()
            week_ago = today - timedelta(days=7)

            # Optimized query with all annotations in one pass
            category_data = (
                Post.objects
                .filter(created_at__date__range=(week_ago, today))
                .annotate(
                    annotated_views_count=Count('interactions', filter=Q(interactions__viewed=True)),
                    annotated_likes_count=Count('interactions', filter=Q(interactions__liked=True)),
                    comments_count=Count('comments'),
                    days_old=now().date() - F('created_at__date'),
                )
                .values('category_id', 'id', 'annotated_views_count', 'annotated_likes_count', 'comments_count', 'days_old')
                .order_by('category_id')
            )

            category_scores = {}
            category_posts = {}

            for post_data in category_data:
                days_old = max(post_data['days_old'].days, 1)
                score = (
                    post_data['annotated_views_count'] + 
                    post_data['annotated_likes_count'] * 2 + 
                    post_data['comments_count'] * 1.5
                ) / days_old

                cat_id = post_data['category_id']
                post_id = post_data['id']
                
                if cat_id not in category_scores:
                    category_scores[cat_id] = []
                    category_posts[cat_id] = []

                category_scores[cat_id].append(score)
                category_posts[cat_id].append((score, post_id))

            # Get all categories in one query
            categories = Category.objects.in_bulk(category_scores.keys())

            category_avg = [
                (sum(scores) / len(scores), categories[cat_id])
                for cat_id, scores in category_scores.items()
                if scores  
            ]

            # Sort categories by average score
            sorted_categories = sorted(category_avg, key=lambda x: x[0], reverse=True)

            # Get all posts in one query
            all_post_ids = [
                post_id 
                for post_list in category_posts.values() 
                for (_, post_id) in post_list
            ]
            posts_map = Post.objects.in_bulk(all_post_ids)

            # Build final category-post map
            category_post_map = []
            for _, cat in sorted_categories:
                posts = category_posts.get(cat.id, [])
                top_3 = sorted(posts, key=lambda x: x[0], reverse=True)[:3]
                top_posts = [posts_map[post_id] for (_, post_id) in top_3]
                category_post_map.append((cat, top_posts))

            # Cache the result for 6 hours
            cache.set('trending_category_map', category_post_map, timeout=21600)

            self.stdout.write(self.style.SUCCESS(
                f"✅ Successfully cached trending posts for {len(category_post_map)} categories"
            ))

        except Exception as e:
            logging.exception("Failed to cache trending category map")
            self.stderr.write(self.style.ERROR(
                f"❌ Failed to cache trending category map: {str(e)}"
            ))