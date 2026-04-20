"""Admin finance read-only queries."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from db.pool import connection


def _sum_completed_orders(cur, where_sql: str = "", params: tuple = ()) -> Decimal:
    cur.execute(f"SELECT COALESCE(SUM(amount), 0) FROM orders WHERE status = %s {where_sql}", ("completed", *params))
    row = cur.fetchone()
    return row[0] or Decimal("0")


def get_finance_breakdown(now: datetime | None = None) -> dict:
    current = now or datetime.now()
    month_start = current.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    today = current.date()

    with connection() as conn:
        if conn is None:
            return {}
        cur = conn.cursor()
        try:
            total_revenue = _sum_completed_orders(cur)
            monthly_revenue = _sum_completed_orders(cur, "AND created_date >= %s", (month_start,))
            today_revenue = _sum_completed_orders(cur, "AND DATE(created_date) = %s", (today,))
            return {
                "total_revenue": total_revenue,
                "monthly_revenue": monthly_revenue,
                "today_revenue": today_revenue,
            }
        finally:
            cur.close()


def calculate_share(amount: Decimal, percent: Decimal = Decimal("0.15")) -> tuple[Decimal, Decimal]:
    share = amount * percent
    return share, amount - share
