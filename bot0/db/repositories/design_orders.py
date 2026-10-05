"""Design order (cover / motion / videoshot brief) queries.

Orders used to live only in an in-memory list and were lost on every restart,
so admin status buttons stopped working. They are stored in design_brief_requests.
"""
from __future__ import annotations

from typing import Any

from psycopg2.extras import Json

from db.pool import connection


_COLUMNS = "d.id, d.user_id, d.service_type, d.title, d.fields, d.status, d.payment_id, d.created_at, l.tg, l.name"


def _row_to_order(row) -> dict[str, Any] | None:
    if row is None:
        return None
    order_id, user_id, service, title, fields, status, payment_id, created_at, tg, name = row
    fields = fields or {}
    display = f"@{tg}" if tg else (name or fields.get("user_display") or str(user_id))
    return {
        "id": str(order_id),
        "user_id": user_id,
        "chat_id": fields.get("chat_id") or user_id,
        "service": service,
        "title": title,
        "details": fields.get("details") or "Бриф не был заполнен",
        "status": status or "принят",
        "payment_id": payment_id,
        "user_display": display,
        "created_at": created_at.isoformat() if created_at else "",
    }


def create_design_order(
    user_id: int,
    service: str,
    details: str,
    title: str,
    chat_id: int | None = None,
    user_display: str | None = None,
    payment_id: str | None = None,
    status: str = "принят",
) -> dict[str, Any] | None:
    with connection() as conn:
        if conn is None:
            return None
        cur = conn.cursor()
        try:
            cur.execute(
                """
                INSERT INTO design_brief_requests (user_id, service_type, title, fields, status, payment_id)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (user_id, service, title, Json({"details": details, "chat_id": chat_id, "user_display": user_display}), status, payment_id),
            )
            order_id = cur.fetchone()[0]
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()
    return get_design_order(order_id)


def get_design_order(order_id) -> dict[str, Any] | None:
    try:
        order_id = int(order_id)
    except (TypeError, ValueError):
        return None
    with connection() as conn:
        if conn is None:
            return None
        cur = conn.cursor()
        try:
            cur.execute(
                f"SELECT {_COLUMNS} FROM design_brief_requests d LEFT JOIN label l ON l.telegram_id = d.user_id WHERE d.id = %s",
                (order_id,),
            )
            return _row_to_order(cur.fetchone())
        finally:
            cur.close()


def update_design_order_status(order_id, status: str) -> dict[str, Any] | None:
    try:
        order_id = int(order_id)
    except (TypeError, ValueError):
        return None
    with connection() as conn:
        if conn is None:
            return None
        cur = conn.cursor()
        try:
            cur.execute(
                "UPDATE design_brief_requests SET status = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s RETURNING id",
                (status, order_id),
            )
            updated = cur.fetchone()
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()
    return get_design_order(order_id) if updated else None


def list_design_orders(service: str | None = None, limit: int = 10) -> list[dict[str, Any]]:
    with connection() as conn:
        if conn is None:
            return []
        cur = conn.cursor()
        try:
            if service:
                cur.execute(
                    f"SELECT {_COLUMNS} FROM design_brief_requests d LEFT JOIN label l ON l.telegram_id = d.user_id "
                    "WHERE d.service_type = %s ORDER BY d.created_at DESC, d.id DESC LIMIT %s",
                    (service, limit),
                )
            else:
                cur.execute(
                    f"SELECT {_COLUMNS} FROM design_brief_requests d LEFT JOIN label l ON l.telegram_id = d.user_id "
                    "ORDER BY d.created_at DESC, d.id DESC LIMIT %s",
                    (limit,),
                )
            return [_row_to_order(row) for row in cur.fetchall()]
        finally:
            cur.close()


def count_design_orders_by_service() -> dict[str, int]:
    with connection() as conn:
        if conn is None:
            return {}
        cur = conn.cursor()
        try:
            cur.execute("SELECT service_type, COUNT(*) FROM design_brief_requests GROUP BY service_type")
            return {service: int(count) for service, count in cur.fetchall()}
        finally:
            cur.close()
