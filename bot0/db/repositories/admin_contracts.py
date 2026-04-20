"""Read-only admin contract queries."""
from __future__ import annotations

from collections import Counter

from db.pool import connection


def _table_exists(cur, table_name: str) -> bool:
    cur.execute("SELECT to_regclass(%s)", (f"public.{table_name}",))
    return cur.fetchone()[0] is not None


def _contract_from_row(row) -> dict:
    return {
        "id": row[0],
        "user_id": row[1],
        "contract_number": row[2],
        "contract_type": row[3],
        "status": row[4],
        "created_at": row[5],
        "completed_at": row[6],
        "contract_file_id": row[7],
        "user_name": row[8],
        "username": row[9],
    }


def list_admin_contracts() -> list[dict]:
    with connection() as conn:
        if conn is None:
            return []
        cur = conn.cursor()
        try:
            if not _table_exists(cur, "contracts"):
                return []
            cur.execute(
                """
                SELECT
                    c.id, c.user_id, c.contract_number, c.contract_type, c.status,
                    c.created_at, c.completed_at, c.contract_file_id,
                    l.name, l.tg
                FROM contracts c
                JOIN label l ON c.user_id = l.telegram_id
                ORDER BY c.created_at DESC
                """
            )
            return [_contract_from_row(row) for row in cur.fetchall()]
        finally:
            cur.close()


def get_admin_contract(contract_id: int) -> dict | None:
    with connection() as conn:
        if conn is None:
            return None
        cur = conn.cursor()
        try:
            if not _table_exists(cur, "contracts"):
                return None
            cur.execute(
                """
                SELECT
                    c.id, c.user_id, c.contract_number, c.contract_type, c.status,
                    c.created_at, c.completed_at, c.contract_file_id,
                    l.name, l.tg
                FROM contracts c
                JOIN label l ON c.user_id = l.telegram_id
                WHERE c.id = %s
                """,
                (contract_id,),
            )
            row = cur.fetchone()
            return _contract_from_row(row) if row else None
        finally:
            cur.close()


def count_contract_statuses(contracts: list[dict]) -> dict:
    counts = Counter(contract.get("status") for contract in contracts)
    return {
        "pending": counts.get("pending", 0),
        "processing": counts.get("processing", 0),
        "completed": counts.get("completed", 0),
        "rejected": counts.get("rejected", 0),
    }

