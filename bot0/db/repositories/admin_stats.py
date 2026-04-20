"""Admin dashboard statistics queries."""
from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

from db.pool import connection


def _table_exists(cur, table_name: str) -> bool:
    cur.execute("SELECT to_regclass(%s)", (f"public.{table_name}",))
    return cur.fetchone()[0] is not None


def get_admin_stats(now: datetime | None = None) -> dict:
    current = now or datetime.now()
    week_ago = current - timedelta(days=7)

    with connection() as conn:
        if conn is None:
            return {}
        cur = conn.cursor()
        try:
            cur.execute("SELECT COUNT(*) FROM label WHERE telegram_id IS NOT NULL")
            total_users = cur.fetchone()[0]

            cur.execute("SELECT COUNT(*) FROM releases WHERE status = %s", ("Релиз",))
            total_releases = cur.fetchone()[0]

            total_bookings = 0
            if _table_exists(cur, "studio_bookings"):
                cur.execute("SELECT COUNT(*) FROM studio_bookings WHERE status = %s", ("completed",))
                total_bookings = cur.fetchone()[0]

            cur.execute("SELECT COALESCE(SUM(amount), 0) FROM orders WHERE status = %s", ("completed",))
            total_revenue = cur.fetchone()[0] or Decimal("0")

            cur.execute("SELECT COUNT(*) FROM reviews WHERE status = %s", ("approved",))
            total_reviews = cur.fetchone()[0]

            cur.execute("SELECT COUNT(*) FROM label WHERE created_date > %s", (week_ago,))
            new_users_week = cur.fetchone()[0]

            return {
                "total_users": int(total_users or 0),
                "total_releases": int(total_releases or 0),
                "total_bookings": int(total_bookings or 0),
                "total_revenue": total_revenue,
                "total_reviews": int(total_reviews or 0),
                "new_users_week": int(new_users_week or 0),
            }
        finally:
            cur.close()
