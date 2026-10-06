"""Versioned consent receipts, separate from accounts and service terms."""
import os
from flask import jsonify, request

VERSION = '2026-10-06'

def register_legal_api(app, get_connection, current_user_id, limiter):
    @app.post('/api/legal/consent')
    @limiter.limit('30 per minute')
    def record_legal_consent():
        if request.headers.get('Origin') not in {os.getenv('AUTH_FRONTEND_URL', 'https://twaslabel.ru').rstrip('/'), 'https://twaslabel.ru', 'https://www.twaslabel.ru'}:
            return jsonify(success=False,error='Недопустимый источник запроса'),403
        data=request.get_json(silent=True) or {}
        if data.get('version') != VERSION or data.get('personal_data') is not True:
            return jsonify(success=False,error='Требуется отдельное согласие'),400
        scope=data.get('scope')
        if not isinstance(scope,str) or len(scope)>80:
            return jsonify(success=False,error='Неверная форма'),400
        conn=get_connection()
        if conn is None:return jsonify(success=False,error='Нет соединения с базой'),503
        try:
            cursor=conn.cursor()
            cursor.execute('INSERT INTO web_legal_consents(user_id,document_version,form_scope,personal_data,terms_accepted) VALUES(%s,%s,%s,true,%s) RETURNING id', (current_user_id(),VERSION,scope,data.get('terms') is True))
            receipt=cursor.fetchone()[0];conn.commit()
            return jsonify(success=True,receipt_id=receipt)
        except Exception:
            conn.rollback();raise
        finally:conn.close()
