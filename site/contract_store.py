"""Shared, idempotent document storage for web and Telegram release submission."""
import base64
import hashlib
import json
import os
from pathlib import Path
from cryptography.fernet import Fernet
from contract_documents import TEMPLATE_VERSION, render_contract


def profile_cipher(secret=None):
    if secret is None:
        secret = os.getenv('SESSION_SECRET') or hashlib.sha256(f"{os.getenv('BOT_TOKEN','')}:{os.getenv('POSTGRES_PASSWORD',os.getenv('DB_PASSWORD',''))}:label-session".encode()).hexdigest()
    return Fernet(os.getenv('CONTRACT_DATA_KEY') or base64.urlsafe_b64encode(hashlib.sha256((str(secret)+':contract-profile').encode()).digest()))


def read_contract_profile(cursor, account, cipher):
    cursor.execute('SELECT encrypted_data FROM release_contract_profiles WHERE user_id=%s',(account,))
    row=cursor.fetchone()
    return json.loads(cipher.decrypt(row['encrypted_data'].encode())) if row else {}


def generate_owned_contract(cursor, account, release_id, storage_root, cipher):
    root=Path(storage_root).resolve()
    cursor.execute('SELECT * FROM releases WHERE id=%s AND user_id=%s FOR UPDATE',(release_id,account))
    release=cursor.fetchone()
    if not release:raise LookupError('Релиз не найден')
    cursor.execute('SELECT * FROM generated_release_contracts WHERE release_id=%s AND user_id=%s',(release_id,account))
    saved=cursor.fetchone()
    if saved:return dict(saved)
    profile=read_contract_profile(cursor,account,cipher)
    cursor.execute('SELECT * FROM releases WHERE album_id=%s AND user_id=%s ORDER BY track_number,id',(release_id,account))
    tracks=cursor.fetchall() if release.get('is_album') else [release]
    tracks=tracks or [release]
    for track in tracks:
        extra=track.get('extra_metadata') or {}
        if isinstance(extra,str):extra=json.loads(extra)
        track['text_author']=extra.get('lyricsAuthors','')
    cover=root/release['cover_local_path'] if release.get('cover_local_path') else None
    if cover and not cover.resolve().is_relative_to(root):cover=None
    output,number=render_contract(profile,release,tracks,cover_path=cover)
    relative=Path('contracts')/f'user_{account}'/f'release_{release_id}.docx'
    path=root/relative
    path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    temporary=path.with_suffix('.tmp')
    with open(temporary,'wb') as file:file.write(output.getvalue())
    os.chmod(temporary,0o600);temporary.replace(path)
    cursor.execute('INSERT INTO generated_release_contracts(release_id,user_id,contract_number,template_version,relative_path) VALUES(%s,%s,%s,%s,%s)',(release_id,account,number,TEMPLATE_VERSION,str(relative)))
    return dict(release_id=release_id,user_id=account,contract_number=number,relative_path=str(relative))
