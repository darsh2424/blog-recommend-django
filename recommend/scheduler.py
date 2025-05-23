from apscheduler.schedulers.background import BackgroundScheduler
from django.core.management import call_command

def start():
    scheduler = BackgroundScheduler()
    # scheduler.add_job(lambda: call_command('precompute_similarity'), 'interval', hours=24)
    scheduler.add_job(lambda: call_command('precompute_similarity'), 'interval', minutes=2)
    scheduler.start()
