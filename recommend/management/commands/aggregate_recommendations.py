from django.db.models.functions import TruncDate
from django.db.models import Count, Q
from django.utils import timezone
from datetime import timedelta, datetime
from blog.models import RecommendationLog, RecommendationStats

def aggregate_recommendations(prune_after_days=None):
    today = timezone.now().date()

    # One query to group all logs by (date, user, tier)
    logs = (
        RecommendationLog.objects
        .annotate(day=TruncDate("created_at"))
        .values("day", "user", "tier")
        .annotate(
            count=Count("id"),
            click_count=Count("id", filter=Q(clicked=True)),
            engage_count=Count("id", filter=Q(engaged=True)),
        )
    )

    for row in logs:
        RecommendationStats.objects.update_or_create(
            user_id=row["user"],
            tier=row["tier"],
            date=row["day"],
            defaults={
                "count": row["count"],
                "click_count": row["click_count"],
                "engage_count": row["engage_count"],
            },
        )

    # prune if needed
    if prune_after_days:
        cutoff = today - timedelta(days=prune_after_days)
        cutoff_dt = timezone.make_aware(datetime.combine(cutoff, datetime.min.time()))
        RecommendationLog.objects.filter(created_at__lt=cutoff_dt).delete()
