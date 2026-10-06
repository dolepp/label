"""Private reusable contract details and release-owned DOCX generation."""
import base64
import hashlib
import json
import os
from contextlib import contextmanager
from pathlib import Path
from cryptography.fernet import Fernet
from flask import jsonify, request, send_file
from psycopg2.extras import RealDictCursor
from contract_documents import FIELDS, REQUIRED, TEMPLATE_VERSION, normalized_profile, render_contract


def register_contract_api(app, get_connection, current_user_id, storage_root):
    cipher = Fernet(os.getenv('CONTRACT_DATA_KEY') or base64.urlsafe_b64encode(hashlib.sha256((str(app.secret_key) + ':contract-profile').encode()).digest()))
    root = Path(storage_root).resolve()

    @contextmanager
    def database():
        conn = get_connection()
        if conn is None: raise ConnectionError('Database unavailable')
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        try:
            yield cursor
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            cursor.close()
            conn.close()

    def read_profile(cursor, account):
        cursor.execute('SELECT encrypted_data FROM release_contract_profiles WHERE user_id=%s', (account,))
        row = cursor.fetchone()
        return json.loads(cipher.decrypt(row['encrypted_data'].encode())) if row else {}

    @app.route('/api/license/profile', methods=['GET', 'PUT'])
    def license_profile():
        account = current_user_id()
        if request.method == 'PUT' and request.headers.get('Origin') not in {os.getenv('AUTH_FRONTEND_URL', 'https://twaslabel.ru').rstrip('/'), 'https://www.twaslabel.ru', 'https://twaslabel.ru'}:
            return jsonify(success=False, error='Недопустимый источник запроса'), 403
        try:
            with database() as cursor:
                if request.method == 'PUT':
                    data = request.get_json(silent=True) or {}
                    if data.get('consent') is not True:
                        return jsonify(success=False, error='Подтвердите согласие на обработку реквизитов'), 400
                    profile = normalized_profile(data.get('profile') or {})
                    encrypted = cipher.encrypt(json.dumps(profile, ensure_ascii=False).encode()).decode()
                    cursor.execute('INSERT INTO release_contract_profiles(user_id,encrypted_data,consent_version) VALUES(%s,%s,%s) ON CONFLICT(user_id) DO UPDATE SET encrypted_data=EXCLUDED.encrypted_data,consent_version=EXCLUDED.consent_version,updated_at=now()', (account, encrypted, '2026-10-06'))
                else: profile = read_profile(cursor, account)
                cursor.execute('SELECT release_id,contract_number,created_at FROM generated_release_contracts WHERE user_id=%s ORDER BY created_at DESC', (account,))
                documents = [dict(row, created_at=row['created_at'].isoformat()) for row in cursor.fetchall()]
            return jsonify(success=True, profile=profile, fields=FIELDS, required=list(REQUIRED), complete=all(profile.get(key) for key in REQUIRED), documents=documents)
        except ValueError as error:
            return jsonify(success=False, error=str(error)), 400

    @app.route('/api/releases/<int:release_id>/license', methods=['POST', 'GET'])
    def release_license(release_id):
        account = current_user_id()
        if request.method == 'POST' and request.headers.get('Origin') not in {os.getenv('AUTH_FRONTEND_URL', 'https://twaslabel.ru').rstrip('/'), 'https://www.twaslabel.ru', 'https://twaslabel.ru'}:
            return jsonify(success=False, error='Недопустимый источник запроса'), 403
        try:
            with database() as cursor:
                cursor.execute('SELECT * FROM releases WHERE id=%s AND user_id=%s FOR UPDATE', (release_id, account))
                release = cursor.fetchone()
                if not release: return jsonify(success=False, error='Релиз не найден'), 404
                cursor.execute('SELECT * FROM generated_release_contracts WHERE release_id=%s AND user_id=%s', (release_id, account))
                saved = cursor.fetchone()
                if request.method == 'GET':
                    if not saved: return jsonify(success=False, error='Договор ещё не сформирован'), 404
                    path = (root / saved['relative_path']).resolve()
                    if not path.is_relative_to(root) or not path.is_file(): return jsonify(success=False, error='Файл не найден'), 404
                    return send_file(path, as_attachment=True, download_name=saved['contract_number'] + '.docx', max_age=0)
                if not saved:
                    profile = read_profile(cursor, account)
                    cursor.execute('SELECT * FROM releases WHERE album_id=%s AND user_id=%s ORDER BY track_number,id', (release_id, account))
                    tracks = cursor.fetchall() if release.get('is_album') else [release]
                    tracks = tracks or [release]
                    for track in tracks:
                        extra = track.get('extra_metadata') or {}
                        if isinstance(extra, str): extra = json.loads(extra)
                        track['text_author'] = extra.get('lyricsAuthors', '')
                    cover = root / release['cover_local_path'] if release.get('cover_local_path') else None
                    if cover and not cover.resolve().is_relative_to(root): cover = None
                    output, number = render_contract(profile, release, tracks, cover_path=cover)
                    relative = Path('contracts') / f'user_{account}' / f'release_{release_id}.docx'
                    path = root / relative
                    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                    temporary = path.with_suffix('.tmp')
                    with open(temporary, 'wb') as file: file.write(output.getvalue())
                    os.chmod(temporary, 0o600)
                    temporary.replace(path)
                    cursor.execute('INSERT INTO generated_release_contracts(release_id,user_id,contract_number,template_version,relative_path) VALUES(%s,%s,%s,%s,%s)', (release_id, account, number, TEMPLATE_VERSION, str(relative)))
                else: number = saved['contract_number']
            return jsonify(success=True, contract_number=number, download_url=f'/api/releases/{release_id}/license', status='draft')
        except ValueError as error:
            return jsonify(success=False, error=str(error)), 400
