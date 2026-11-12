from django.db import connection
from django.http import JsonResponse


def readiness(_request):
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        existing = set(connection.introspection.table_names())
        essential = {"accounts_user", "market_provider", "scraping_scraperun"}
        ready = essential.issubset(existing)
    except Exception:
        ready = False
    return JsonResponse({"status": "ready" if ready else "not-ready"}, status=200 if ready else 503)
