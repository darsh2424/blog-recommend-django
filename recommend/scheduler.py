from apscheduler.schedulers.background import BackgroundScheduler
from django.core.management import call_command
import logging

logger = logging.getLogger(__name__)

def start():
    scheduler = BackgroundScheduler()
    def import_once_if_empty():
        from blog.models import Post
        if not Post.objects.exists():
            call_command('import_blogs_from_csv_testing')
            call_command('precompute_similarity')
            call_command('cache_trending_categories')

    import_once_if_empty()
    scheduler.add_job(lambda: call_command('precompute_similarity'), 'interval', hours=6)
    scheduler.add_job(lambda: call_command('cache_trending_categories'), 'interval', hours=6)
    logger.info("✅ APScheduler started: precompute_similarity and cache_trending_categories run every 6 hours")

    scheduler.start()