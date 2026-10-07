"""Owner-controlled public listening pages; only public metadata is exposed."""
import os
import re
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlsplit
from flask import jsonify,request,send_file
from psycopg2.extras import Json, RealDictCursor
PLATFORMS={
 'yandex':('Яндекс Музыка',{'music.yandex.ru','music.yandex.com','music.yandex.kz','music.yandex.by'}),
 'vk':('VK Музыка',{'vk.com','vk.ru','music.vk.com','music.vk.ru','boom.ru'}),
 'apple':('Apple Music',{'music.apple.com','itunes.apple.com'}),
 'spotify':('Spotify',{'open.spotify.com'}),'zvuk':('Звук',{'zvuk.com'}),
 'deezer':('Deezer',{'deezer.com','www.deezer.com'}),
 'youtube':('YouTube Music',{'music.youtube.com','www.youtube.com','youtube.com','youtu.be'}),
 'amazon':('Amazon Music',{'music.amazon.com','music.amazon.co.uk','music.amazon.de'}),
 'mts':('МТС Музыка',{'music.mts.ru'})}


def validate_links(data):
    if not isinstance(data,dict):raise ValueError('Ожидается список ссылок.')
    result={}
    for key,value in data.items():
        if key not in PLATFORMS:raise ValueError('Неизвестная площадка.')
        if not isinstance(value,str):raise ValueError('Ссылка должна быть текстом.')
        value=value.strip()
        if not value:continue
        try:parsed=urlsplit(value);port=parsed.port
        except ValueError:raise ValueError('Некорректная ссылка.')
        if len(value)>2048 or any(ord(char)<33 for char in value) or parsed.scheme!='https' or parsed.hostname not in PLATFORMS[key][1] or parsed.username or parsed.password or port not in {None,443}:
            raise ValueError('Укажите HTTPS-ссылку самой площадки: '+PLATFORMS[key][0])
        result[key]=value
    if not result:raise ValueError('Добавьте хотя бы одну ссылку на площадку.')
    return result


def suggested_links(data):
    result={}
    if not isinstance(data,dict):return result
    for value in data.values():
        if not isinstance(value,str):continue
        for key,(_,hosts) in PLATFORMS.items():
            try:
                if urlsplit(value).hostname in hosts:result.update(validate_links({key:value}))
            except ValueError:pass
    return result


def register_smartlinks_api(app,get_connection,current_user_id,storage_root,proxy_telegram_file):
    root=Path(storage_root).resolve()
    public_base=os.getenv('SMARTLINK_PUBLIC_BASE','https://twaslabel.ru').rstrip('/')
    @contextmanager
    def database():
        conn=get_connection()
        if not conn:raise ConnectionError('Database unavailable')
        cursor=conn.cursor(cursor_factory=RealDictCursor)
        try:yield cursor;conn.commit()
        except Exception:conn.rollback();raise
        finally:cursor.close();conn.close()

    def public_release(cursor,slug):
        cursor.execute('SELECT s.slug,s.platform_links,r.id AS release_id,r.release_name,r.artist_name,r.release_date,r.cover_local_path,r.cover_file_id FROM release_smartlinks s JOIN releases r ON r.id=s.release_id WHERE s.slug=%s AND s.published=true',(slug,))
        return cursor.fetchone()

    @app.route('/api/releases/<int:release_id>/smartlink',methods=['GET','PUT'])
    def owned_smartlink(release_id):
        account=current_user_id()
        if request.method=='PUT' and request.headers.get('Origin') not in {os.getenv('AUTH_FRONTEND_URL','https://twaslabel.ru').rstrip('/'),'https://twaslabel.ru','https://www.twaslabel.ru'}:
            return jsonify(success=False,error='Недопустимый источник запроса'),403
        try:
            with database() as cursor:
                cursor.execute('SELECT * FROM releases WHERE id=%s AND user_id=%s',(release_id,account));release=cursor.fetchone()
                if not release:return jsonify(success=False,error='Релиз не найден'),404
                cursor.execute('SELECT * FROM release_smartlinks WHERE release_id=%s AND user_id=%s',(release_id,account));saved=cursor.fetchone()
                if request.method=='PUT':
                    data=request.get_json(silent=True) or {}
                    if not isinstance(data,dict):raise ValueError('Ожидаются настройки ссылки.')
                    slug=data.get('slug','')
                    if not isinstance(slug,str) or not re.fullmatch(r'[a-z0-9][a-z0-9_-]{2,79}',slug):raise ValueError('Адрес: 3–80 строчных латинских букв, цифр, дефисов или подчёркиваний.')
                    links=validate_links(data.get('platform_links',{}))
                    published=data.get('published',True)
                    if type(published) is not bool:raise ValueError('Неверный статус публикации.')
                    cursor.execute('SELECT release_id FROM release_smartlinks WHERE slug=%s',(slug,));occupied=cursor.fetchone()
                    if occupied and occupied['release_id']!=release_id:return jsonify(success=False,error='Этот адрес уже занят'),409
                    cursor.execute('INSERT INTO release_smartlinks(release_id,user_id,slug,platform_links,published) VALUES(%s,%s,%s,%s,%s) ON CONFLICT(release_id) DO UPDATE SET slug=EXCLUDED.slug,platform_links=EXCLUDED.platform_links,published=EXCLUDED.published,updated_at=now() RETURNING *',(release_id,account,slug,Json(links),published));saved=cursor.fetchone()
                cursor.execute("SELECT platform,count(*) AS total FROM website_analytics_events WHERE release_id=%s AND event_type='platform_click' AND created_at>now()-interval '30 days' GROUP BY platform",(release_id,));clicks=[dict(row) for row in cursor.fetchall()]
            document=dict(saved) if saved else {'slug':f'release-{release_id}','platform_links':suggested_links(release.get('platform_links')),'published':False}
            for key in ['created_at','updated_at']:
                if key in document:document[key]=document[key].isoformat()
            document['url']=public_base+'/l/'+document['slug']
            return jsonify(success=True,smartlink=document,platforms={key:value[0] for key,value in PLATFORMS.items()},clicks=clicks)
        except ValueError as error:return jsonify(success=False,error=str(error)),400
        except Exception as error:
            if getattr(error,'pgcode',None)=='23505':return jsonify(success=False,error='Этот адрес уже занят'),409
            raise

    @app.get('/api/smartlinks/<slug>')
    def get_public_smartlink(slug):
        with database() as cursor:row=public_release(cursor,slug)
        if not row:return jsonify(success=False,error='Ссылка не найдена или скрыта владельцем'),404
        return jsonify(success=True,release={'id':row['release_id'],'title':row['release_name'],'artist':row['artist_name'],'release_date':row['release_date'].isoformat() if row['release_date'] else None,'cover_url':f'/api/smartlinks/{slug}/cover'},links=[{'key':key,'label':PLATFORMS[key][0],'url':value} for key,value in row['platform_links'].items() if key in PLATFORMS],slug=slug)

    @app.get('/api/smartlinks/<slug>/cover')
    def smartlink_cover(slug):
        with database() as cursor:row=public_release(cursor,slug)
        if not row:return jsonify(success=False,error='Обложка не найдена'),404
        if row['cover_local_path']:
            path=(root/row['cover_local_path']).resolve()
            if path.is_relative_to(root) and path.is_file():return send_file(path,conditional=True)
        if row['cover_file_id']:return proxy_telegram_file(row['cover_file_id'],'image/jpeg')
        return jsonify(success=False,error='Обложка не загружена'),404
