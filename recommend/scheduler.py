from apscheduler.schedulers.background import BackgroundScheduler
from django.core.management import call_command
import logging

logger = logging.getLogger(__name__)

def start():
    scheduler = BackgroundScheduler()
    scheduler.add_job(lambda: call_command('precompute_similarity'), 'interval', hours=6)
    scheduler.add_job(lambda: call_command('cache_trending_categories'), 'interval', hours=6)
    logger.info("✅ APScheduler started: precompute_similarity and cache_trending_categories run every 6 hours")

    scheduler.start()