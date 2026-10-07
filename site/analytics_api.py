"""Counter configuration and anonymous, consent-only product events."""
import os
import re
from ipaddress import ip_address
from contextlib import contextmanager
from flask import jsonify,request
from psycopg2.extras import Json, RealDictCursor
VERSION='2026-10-07'
CONFIG_FIELDS={'yandex_id':r'\d{1,12}','google_id':r'G-[A-Z0-9]{4,30}','vk_id':r'\d{1,18}','meta_id':r'\d{1,22}'}
EVENTS={'page_view','auth_success','release_submitted','checkout_started','payment_success','tool_open','ttml_completed','ttml_download','ttml_attached','video_exported','smartlink_created','platform_click'}
CONTEXTS={'','home','services','tools','profile','releases','promos','teleprompter','ttml','smartlink','legal','lyrics_video'}
PLATFORMS={'','yandex','vk','apple','spotify','zvuk','deezer','youtube','amazon','mts'}


def analytics_rate_key():
    peer=request.remote_addr or 'unknown'
    # Local nginx overwrites X-Real-IP; ignore forwarding headers from other peers.
    if peer in {'127.0.0.1','::1'}:
        try:return str(ip_address(request.headers.get('X-Real-IP','')))
        except ValueError:pass
    return peer


def clean_config(data):
    if not isinstance(data,dict):raise ValueError('Ожидаются настройки счётчиков.')
    result={}
    for key,pattern in CONFIG_FIELDS.items():
        value=data.get(key,'')
        if not isinstance(value,str):raise ValueError('Идентификатор счётчика должен быть строкой.')
        value=value.strip()
        if value and not re.fullmatch(pattern,value):raise ValueError('Неверный идентификатор: '+key)
        result[key]=value
    return result


def register_analytics_api(app,get_connection,current_user_id,limiter):
    @contextmanager
    def database():
        conn=get_connection()
        if not conn:raise ConnectionError('Database unavailable')
        cursor=conn.cursor(cursor_factory=RealDictCursor)
        try:yield cursor;conn.commit()
        except Exception:conn.rollback();raise
        finally:cursor.close();conn.close()

    def config(cursor):
        cursor.execute('SELECT configuration FROM website_analytics_settings WHERE id=1')
        row=cursor.fetchone()
        return clean_config(row['configuration'] if row else {key:os.getenv('ANALYTICS_'+key.upper(),'') for key in CONFIG_FIELDS})

    @app.get('/api/analytics/config')
    def analytics_config():
        with database() as cursor:configuration=config(cursor)
        return jsonify(success=True,configuration=configuration,consent_version=VERSION)

    @app.route('/api/admin/analytics',methods=['GET','PUT'])
    def admin_analytics():
        if request.method=='PUT' and request.headers.get('Origin') not in {os.getenv('AUTH_FRONTEND_URL','https://twaslabel.ru').rstrip('/'),'https://twaslabel.ru','https://www.twaslabel.ru'}:
            return jsonify(success=False,error='Недопустимый источник запроса'),403
        try:
            with database() as cursor:
                if request.method=='PUT':
                    configuration=clean_config(request.get_json(silent=True) or {})
                    cursor.execute('INSERT INTO website_analytics_settings(id,configuration) VALUES(1,%s) ON CONFLICT(id) DO UPDATE SET configuration=EXCLUDED.configuration,updated_at=now()',(Json(configuration),))
                else:configuration=config(cursor)
                cursor.execute("SELECT event_type,count(*) AS total FROM website_analytics_events WHERE created_at>now()-interval '30 days' GROUP BY event_type ORDER BY total DESC")
                events=[dict(row) for row in cursor.fetchall()]
                cursor.execute("SELECT platform,count(*) AS total FROM website_analytics_events WHERE event_type='platform_click' AND created_at>now()-interval '30 days' GROUP BY platform ORDER BY total DESC")
                platforms=[dict(row) for row in cursor.fetchall()]
            return jsonify(success=True,configuration=configuration,events=events,platforms=platforms,days=30)
        except ValueError as error:return jsonify(success=False,error=str(error)),400

    @app.post('/api/analytics/event')
    @limiter.limit('60 per minute',key_func=analytics_rate_key)
    def analytics_event():
        if request.headers.get('Origin') not in {os.getenv('AUTH_FRONTEND_URL','https://twaslabel.ru').rstrip('/'),'https://twaslabel.ru','https://www.twaslabel.ru'}:
            return jsonify(success=False,error='Недопустимый источник запроса'),403
        data=request.get_json(silent=True) or {}
        if not isinstance(data,dict):return jsonify(success=False,error='Ожидается событие'),400
        if data.get('analytics_consent') is not True or data.get('consent_version')!=VERSION:
            return jsonify(success=False,error='Нет согласия на аналитику'),400
        if not all(isinstance(data.get(key,''),str) for key in ['event','context','platform']):return jsonify(success=False,error='Неверное событие'),400
        if data.get('event') not in EVENTS or data.get('context','') not in CONTEXTS or data.get('platform','') not in PLATFORMS:
            return jsonify(success=False,error='Недопустимое событие'),400
        release_id=data.get('release_id')
        if release_id is not None and (type(release_id) is not int or release_id<=0):return jsonify(success=False,error='Неверный релиз'),400
        with database() as cursor:
            cursor.execute('INSERT INTO website_analytics_events(event_type,context,release_id,platform) VALUES(%s,%s,%s,%s)',(data['event'],data.get('context',''),release_id,data.get('platform','')))
            cursor.execute("DELETE FROM website_analytics_events WHERE created_at<now()-interval '90 days'")
        return jsonify(success=True),202
