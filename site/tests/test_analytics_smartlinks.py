"""Isolated PostgreSQL integration; no live accounts or tracker requests."""
import os,secrets,sys,tempfile,unittest
from pathlib import Path
from flask import Flask,session
import psycopg2
from psycopg2 import sql
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from analytics_api import register_analytics_api,clean_config,analytics_rate_key
from smartlinks_api import register_smartlinks_api,validate_links
class NoLimiter:
 def limit(self,_,**kwargs):return lambda f:f
class InputTests(unittest.TestCase):
 def test_rate_limit_trusts_only_local_proxy(self):
  app=Flask(__name__)
  for peer,forwarded,expected in [('127.0.0.1','203.0.113.4','203.0.113.4'),('127.0.0.1','invalid','127.0.0.1'),('203.0.113.5','203.0.113.4','203.0.113.5')]:
   with app.test_request_context(headers={'X-Real-IP':forwarded},environ_base={'REMOTE_ADDR':peer}):
    self.assertEqual(analytics_rate_key(),expected)
 def test_configuration_and_platform_validation(self):
  self.assertEqual(clean_config({'google_id':'G-ABC123'})['google_id'],'G-ABC123')
  for value in ['<script>','not-an-id',5]:
   with self.assertRaises(ValueError):clean_config({'yandex_id':value})
  self.assertEqual(validate_links({'spotify':'https://open.spotify.com/album/example'})['spotify'],'https://open.spotify.com/album/example')
  for value in ['javascript:alert(1)','https://open.spotify.com.evil.test/a','https://user:pass@open.spotify.com/a','https://open.spotify.com:1234/a','http://open.spotify.com/a']:
   with self.assertRaises(ValueError):validate_links({'spotify':value})

@unittest.skipUnless(os.getenv('TEST_AUTH_POSTGRES')=='1','Requires PostgreSQL test schema')
class AnalyticsSmartlinksTests(unittest.TestCase):
 @classmethod
 def connect(cls):
  conn=psycopg2.connect(**cls.config)
  with conn.cursor() as cursor:cursor.execute(sql.SQL('SET search_path TO {}').format(sql.Identifier(cls.schema)))
  conn.commit();return conn
 @classmethod
 def setUpClass(cls):
  cls.config=dict(dbname=os.getenv('POSTGRES_DB','label'),user=os.getenv('POSTGRES_USER','postgres'),password=os.getenv('POSTGRES_PASSWORD',''),host=os.getenv('POSTGRES_HOST','localhost'),port=os.getenv('POSTGRES_PORT','5432'))
  cls.schema='smartlink_test_'+secrets.token_hex(6);conn=psycopg2.connect(**cls.config)
  with conn.cursor() as cursor:cursor.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(cls.schema)))
  conn.commit();conn.close();conn=cls.connect()
  with conn.cursor() as cursor:
   cursor.execute('CREATE TABLE releases(id BIGINT PRIMARY KEY,user_id BIGINT,release_name TEXT,artist_name TEXT,release_date DATE,cover_local_path TEXT,cover_file_id TEXT,platform_links JSONB)')
   cursor.execute("INSERT INTO releases(id,user_id,release_name,artist_name,release_date) VALUES(1,-42,'Test release','Test artist','2026-10-07'),(2,123,'Other','Other',NULL)")
   cursor.execute((Path(__file__).resolve().parents[2]/'migrations/007_analytics_smartlinks.sql').read_text().replace('BEGIN;','').replace('COMMIT;',''))
  conn.commit();conn.close();cls.directory=tempfile.TemporaryDirectory();cls.app=Flask(__name__);cls.app.secret_key='test';cls.app.testing=True
  register_analytics_api(cls.app,cls.connect,lambda:session.get('user_id'),NoLimiter())
  register_smartlinks_api(cls.app,cls.connect,lambda:session.get('user_id'),cls.directory.name,lambda *args:(_ for _ in ()).throw(AssertionError('No live Telegram calls')))
 @classmethod
 def tearDownClass(cls):
  cls.directory.cleanup();conn=psycopg2.connect(**cls.config)
  with conn.cursor() as cursor:cursor.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(cls.schema)))
  conn.commit();conn.close()
 def test_ownership_public_fields_slug_collision_and_stats(self):
  client=self.app.test_client();origin={'Origin':'https://twaslabel.ru'}
  with client.session_transaction() as data:data['user_id']=-42
  self.assertEqual(client.get('/api/releases/2/smartlink').status_code,404)
  values={'slug':'test_release','platform_links':{'yandex':'https://music.yandex.ru/album/123'},'published':True}
  self.assertEqual(client.put('/api/releases/1/smartlink',json=values).status_code,403)
  result=client.put('/api/releases/1/smartlink',json=values,headers=origin);self.assertEqual(result.status_code,200,result.json)
  self.assertEqual(client.put('/api/releases/2/smartlink',json=values,headers=origin).status_code,404)
  public=client.get('/api/smartlinks/test_release').json
  self.assertEqual(public['release']['title'],'Test release');self.assertNotIn('user_id',str(public));self.assertNotIn('audio',str(public));self.assertNotIn('passport',str(public))
  with client.session_transaction() as data:data['user_id']=123
  self.assertEqual(client.put('/api/releases/2/smartlink',json=values,headers=origin).status_code,409)
  event={'event':'platform_click','context':'smartlink','platform':'yandex','release_id':1,'consent_version':'2026-10-07','analytics_consent':False}
  self.assertEqual(client.post('/api/analytics/event',json=event,headers=origin).status_code,400)
  event['analytics_consent']=True
  self.assertEqual(client.post('/api/analytics/event',json=event).status_code,403)
  self.assertEqual(client.post('/api/analytics/event',json=event,headers=origin).status_code,202)
  event['event']='unlisted-event';self.assertEqual(client.post('/api/analytics/event',json=event,headers=origin).status_code,400)
  with client.session_transaction() as data:data['user_id']=-42
  self.assertEqual(client.get('/api/releases/1/smartlink').json['clicks'][0]['total'],1)
  values['published']=False;self.assertEqual(client.put('/api/releases/1/smartlink',json=values,headers=origin).status_code,200)
  self.assertEqual(client.get('/api/smartlinks/test_release').status_code,404)
 def test_counter_configuration(self):
  client=self.app.test_client();origin={'Origin':'https://twaslabel.ru'}
  self.assertEqual(client.put('/api/admin/analytics',json={'google_id':'invalid'},headers=origin).status_code,400)
  self.assertEqual(client.put('/api/admin/analytics',json={'google_id':'G-TEST123'},headers=origin).status_code,200)
  self.assertEqual(client.get('/api/analytics/config').json['configuration']['google_id'],'G-TEST123')
if __name__=='__main__':unittest.main()
