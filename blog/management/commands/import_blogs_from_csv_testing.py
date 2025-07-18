import random
from datetime import timedelta
from pathlib import Path

import pandas as pd
from django.core.management.base import BaseCommand
from django.utils.timezone import now
from django.db.models import Count, Q

from blog.models import Category, Post
from users.models import User, UserProfile, PostInteraction

BASE_DIR = Path(__file__).resolve().parent  
DATA_FILE = BASE_DIR / "Medium_Blog_Data.csv"
MAX_BLOGS = 200  # Total blog post limit

class Command(BaseCommand):
    help = 'Import Medium blog data into the system with a cap of 200 blog posts.'

    def handle(self, *args, **kwargs):
        if Post.objects.exists():
            self.stdout.write(self.style.WARNING("⚠️ Posts already exist. Import skipped."))
            return
        
        if not DATA_FILE.exists():
            self.stdout.write(self.style.ERROR(f"File not found: {DATA_FILE.resolve()}"))
            return

        df = pd.read_csv(DATA_FILE)

        # Drop rows missing critical fields
        df = df.dropna(subset=['blog_title', 'blog_content', 'topic'])

        # Use top 10 most common topics
        top_topics = df['topic'].value_counts().head(10).index.tolist()
        blogs_per_topic = MAX_BLOGS // len(top_topics)

        total_created = 0
        categories = {}
        user_map = {}

        for topic in top_topics:
            category, _ = Category.objects.get_or_create(name=topic.strip())
            categories[topic] = category

            # Create 2 demo users per category
            demo_users = []
            for i in range(1, 3):
                uname = f"{topic.lower().replace(' ', '_')}_user_{i}"
                email = f"{uname}@example.com"
                user, created = User.objects.get_or_create(email=email)
                if created:
                    user.username = uname
                    user.set_unusable_password()
                    user.save()
                    UserProfile.objects.create(user=user, full_name=uname)
                demo_users.append(user)
            user_map[topic] = demo_users

            # Select up to blogs_per_topic posts for this topic
            topic_df = df[df['topic'] == topic].sample(frac=1).head(blogs_per_topic)

            for _, row in topic_df.iterrows():
                title = row['blog_title'][:255]
                content = row['blog_content']
                image_url = row.get('blog_img', None)
                user = random.choice(user_map[topic])
                random_date = now() - timedelta(days=random.randint(0, 365))

                # Create the post without counters
                post = Post.objects.create(
                    user=user,
                    title=title,
                    content=content,
                    image_url=image_url if pd.notnull(image_url) else None,
                    category=category,
                    created_at=random_date
                )

                # Simulate some interactions
                self._create_interactions(post, user_map)
                total_created += 1

                if total_created >= MAX_BLOGS:
                    break

            if total_created >= MAX_BLOGS:
                break

        self.stdout.write(self.style.SUCCESS(f"Successfully imported {total_created} blog posts."))

    def _create_interactions(self, post, user_map):
        """Create simulated interactions for the new post"""
        # Get all users except the post author
        all_users = []
        for users in user_map.values():
            all_users.extend(users)
        other_users = [u for u in all_users if u != post.user]
        
        # Randomly select some users to view the post
        viewers = random.sample(other_users, min(10, len(other_users)))
        for user in viewers:
            PostInteraction.objects.create(
                user=user,
                post=post,
                viewed=True,
                timestamp=post.created_at + timedelta(minutes=random.randint(1, 1440))
            )
        
        # Randomly select some users to like the post (subset of viewers)
        likers = random.sample(viewers, min(5, len(viewers)))
        for user in likers:
            PostInteraction.objects.update_or_create(
                user=user,
                post=post,
                defaults={'liked': True}
            )