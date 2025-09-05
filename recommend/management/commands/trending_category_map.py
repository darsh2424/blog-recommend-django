
from django.db.models import Count
from django.utils import timezone
from datetime import timedelta
from blog.models import RecommendationLog, RecommendationStats


def aggregate_recommendations(days_back=1, prune_after_days=30):
    """
    Aggregate recommendation logs into stats for the past 'days_back' days.
    Also prune logs older than 'prune_after_days'.
    """
    today = timezone.now().date()
    start_date = today - timedelta(days=days_back)

    # Loop through each day we want to aggregate
    for d in range(days_back):
        day = today - timedelta(days=d + 1)

        logs = (
            RecommendationLog.objects.filter(created_at__date=day)
            .values("user", "tier")
            .annotate(count=Count("id"))
        )

        for row in logs:
            RecommendationStats.objects.update_or_create(
                user_id=row["user"],
                tier=row["tier"],
                date=day,
                defaults={"count": row["count"]},
            )

    # === Optional pruning ===
    cutoff = today - timedelta(days=prune_after_days)
    RecommendationLog.objects.filter(created_at__lt=cutoff).delete()
