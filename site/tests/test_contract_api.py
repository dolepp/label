"""Isolated PostgreSQL tests; never reads live users or generates live contracts."""
import os
import secrets
import sys
import tempfile
import unittest
from pathlib import Path
import psycopg2
from psycopg2 import sql
from flask import Flask,session
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from contract_api import register_contract_api
from test_contract_documents import PROFILE

@unittest.skipUnless(os.getenv('TEST_AUTH_POSTGRES')=='1','Requires PostgreSQL test connection')
class ContractApiTests(unittest.TestCase):
    @classmethod
    def connect(cls):
        conn=psycopg2.connect(**cls.config)
        with conn.cursor() as cursor:cursor.execute(sql.SQL('SET search_path TO {}').format(sql.Identifier(cls.schema)))
        conn.commit();return conn
    @classmethod
    def setUpClass(cls):
        cls.config=dict(dbname=os.getenv('POSTGRES_DB','label'),user=os.getenv('POSTGRES_USER','postgres'),password=os.getenv('POSTGRES_PASSWORD',''),host=os.getenv('POSTGRES_HOST','localhost'),port=os.getenv('POSTGRES_PORT','5432'))
        cls.schema='contract_test_'+secrets.token_hex(6)
        conn=psycopg2.connect(**cls.config)
        with conn.cursor() as cursor:cursor.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(cls.schema)))
        conn.commit();conn.close()
        conn=cls.connect()
        with conn.cursor() as cursor:
            cursor.execute('CREATE TABLE releases(id BIGINT PRIMARY KEY,user_id BIGINT,release_name TEXT,artist_name TEXT,music_author TEXT,performer_name TEXT,release_date DATE,album_id BIGINT,is_album BOOLEAN,track_number INTEGER,extra_metadata JSONB,cover_local_path TEXT)')
            cursor.execute((Path(__file__).resolve().parents[2]/'migrations/006_release_contracts.sql').read_text().replace('BEGIN;','').replace('COMMIT;',''))
            cursor.execute("INSERT INTO releases(id,user_id,release_name,artist_name,is_album) VALUES(1,-42,'Тест','Тест',false),(2,123,'Чужой','Тест',false)")
        conn.commit();conn.close()
        cls.directory=tempfile.TemporaryDirectory()
        cls.app=Flask(__name__);cls.app.secret_key='test-contract';cls.app.testing=True
        def current():return session.get('user_id')
        register_contract_api(cls.app,cls.connect,current,cls.directory.name)
    @classmethod
    def tearDownClass(cls):
        cls.directory.cleanup();conn=psycopg2.connect(**cls.config)
        with conn.cursor() as cursor:cursor.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(cls.schema)))
        conn.commit();conn.close()
    def test_private_encrypted_idempotent_contract(self):
        client=self.app.test_client()
        with client.session_transaction() as session_data:session_data['user_id']=-42
        origin={'Origin':'https://twaslabel.ru'}
        self.assertEqual(client.put('/api/license/profile',json={'profile':PROFILE,'consent':True}).status_code,403)
        self.assertEqual(client.put('/api/license/profile',json={'profile':PROFILE,'consent':False},headers=origin).status_code,400)
        self.assertEqual(client.put('/api/license/profile',json={'profile':PROFILE,'consent':True},headers=origin).status_code,200)
        conn=self.connect()
        with conn.cursor() as cursor:
            cursor.execute('SELECT encrypted_data FROM release_contract_profiles WHERE user_id=-42');encrypted=cursor.fetchone()[0]
            self.assertNotIn(PROFILE['passport'],encrypted)
            self.assertNotIn(PROFILE['full_name'],encrypted)
        conn.close()
        self.assertEqual(client.post('/api/releases/2/license',headers=origin).status_code,404)
        self.assertEqual(client.get('/api/releases/2/license').status_code,404)
        first=client.post('/api/releases/1/license',headers=origin)
        self.assertEqual(first.status_code,200,first.json)
        second=client.post('/api/releases/1/license',headers=origin)
        self.assertEqual(first.json['contract_number'],second.json['contract_number'])
        download=client.get('/api/releases/1/license')
        self.assertEqual(download.status_code,200)
        self.assertTrue(download.data.startswith(b'PK'))
        conn=self.connect()
        with conn.cursor() as cursor:cursor.execute('SELECT count(*) FROM generated_release_contracts');self.assertEqual(cursor.fetchone()[0],1)
        conn.close()
        self.assertEqual(client.get('/api/license/profile').json['profile']['full_name'],PROFILE['full_name'])
