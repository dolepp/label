"""User contract read queries."""
from __future__ import annotations

from db.pool import connection


def _table_exists(cur, table_name: str) -> bool:
    cur.execute("SELECT to_regclass(%s)", (f"public.{table_name}",))
    return cur.fetchone()[0] is not None


def _contract_from_row(row) -> dict:
    return {
        "id": row[0],
        "contract_number": row[1],
        "contract_type": row[2],
        "status": row[3],
        "created_at": row[4],
        "completed_at": row[5],
        "contract_file_id": row[6],
        "user_id": row[7],
    }


def list_user_contracts(user_id: int) -> list[dict]:
    with connection() as conn:
        if conn is None:
            return []
        cur = conn.cursor()
        try:
            if not _table_exists(cur, "contracts"):
                return []
            cur.execute(
                """
                SELECT id, contract_number, contract_type, status, created_at, completed_at, contract_file_id, user_id
                FROM contracts
                WHERE user_id = %s
                ORDER BY created_at DESC
                """,
                (user_id,),
            )
            return [_contract_from_row(row) for row in cur.fetchall()]
        finally:
            cur.close()


def get_user_contract(contract_id: int, user_id: int) -> dict | None:
    with connection() as conn:
        if conn is None:
            return None
        cur = conn.cursor()
        try:
            if not _table_exists(cur, "contracts"):
                return None
            cur.execute(
                """
                SELECT id, contract_number, contract_type, status, created_at, completed_at, contract_file_id, user_id
                FROM contracts
                WHERE id = %s AND user_id = %s
                """,
                (contract_id, user_id),
            )
            row = cur.fetchone()
            return _contract_from_row(row) if row else None
        finally:
            cur.close()
