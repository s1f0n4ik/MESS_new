import tempfile
import unittest
from pathlib import Path
from fastapi import FastAPI
from fastapi.testclient import TestClient
from mediation_bridge import create_router


class MediationBridgeTests(unittest.TestCase):
    def test_selection_is_shared_per_run_and_survives_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            app=FastAPI();app.include_router(create_router(root))
            client=TestClient(app)
            self.assertIsNone(client.get('/api/mediation/current?runKey=100').json().get('projectId'))
            self.assertEqual(client.post('/api/mediation/current',json={'runKey':'100','projectId':42,'title':'Группа А'}).status_code,200)
            self.assertEqual(client.get('/api/mediation/current?runKey=100').json()['projectId'],42)
            self.assertIsNone(client.get('/api/mediation/current?runKey=101').json().get('projectId'))
            again=FastAPI();again.include_router(create_router(root))
            self.assertEqual(TestClient(again).get('/api/mediation/current?runKey=100').json()['projectId'],42)
            self.assertEqual(client.post('/api/mediation/current',json={'runKey':'../bad','projectId':42,'title':'bad'}).status_code,422)
