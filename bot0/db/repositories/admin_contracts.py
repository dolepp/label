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



def update_contract_status(contract_id: int, status: str) -> dict | None:
    with connection() as conn:
        if conn is None:
            return None
        cur = conn.cursor()
        try:
            cur.execute("UPDATE contracts SET status = %s WHERE id = %s RETURNING id", (status, contract_id))
            if not cur.fetchone():
                conn.rollback()
                return None
            conn.commit()
            return get_admin_contract(contract_id)
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()


def attach_contract_file(contract_id: int, file_id: str) -> dict | None:
    with connection() as conn:
        if conn is None:
            return None
        cur = conn.cursor()
        try:
            cur.execute(
                "UPDATE contracts SET contract_file_id = %s WHERE id = %s RETURNING id",
                (file_id, contract_id),
            )
            if not cur.fetchone():
                conn.rollback()
                return None
            conn.commit()
            return get_admin_contract(contract_id)
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()


def complete_contract(contract_id: int) -> dict | None:
    with connection() as conn:
        if conn is None:
            return None
        cur = conn.cursor()
        try:
            cur.execute("SELECT contract_file_id FROM contracts WHERE id = %s", (contract_id,))
            row = cur.fetchone()
            if not row:
                conn.rollback()
                return None
            if not row[0]:
                conn.rollback()
                return {"id": contract_id, "missing_file": True}
            cur.execute(
                "UPDATE contracts SET status = 'completed', completed_at = NOW() WHERE id = %s RETURNING id",
                (contract_id,),
            )
            conn.commit()
            return get_admin_contract(contract_id)
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()


def user_owns_contract(contract_id: int, user_id: int) -> bool:
    with connection() as conn:
        if conn is None:
            return False
        cur = conn.cursor()
        try:
            if not _table_exists(cur, "contracts"):
                return False
            cur.execute("SELECT 1 FROM contracts WHERE id = %s AND user_id = %s", (contract_id, user_id))
            return cur.fetchone() is not None
        finally:
            cur.close()
