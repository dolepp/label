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


def create_contract_request(user_id: int, contract_type: str = "standard", notes: str | None = None) -> dict | None:
    """Заявка на договор — тот же формат, что создаёт сайт (CTR-YYYYMMDD-id)."""
    with connection() as conn:
        if conn is None:
            return None
        cur = conn.cursor()
        try:
            cur.execute(
                """
                INSERT INTO contracts (user_id, contract_type, status, notes, created_at, updated_at)
                VALUES (%s, %s, 'pending', %s, NOW(), NOW())
                RETURNING id, created_at
                """,
                (user_id, contract_type, notes),
            )
            contract_id, created_at = cur.fetchone()
            contract_number = f"CTR-{created_at.strftime('%Y%m%d')}-{contract_id}"
            cur.execute("UPDATE contracts SET contract_number = %s WHERE id = %s", (contract_number, contract_id))
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()
    return get_user_contract(contract_id, user_id)
