import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
import requests

spec = importlib.util.spec_from_file_location('smartseat_connector', Path(__file__).resolve().parents[1] / 'connector/ensure_connection.py')
connector = importlib.util.module_from_spec(spec)
spec.loader.exec_module(connector)

class ConnectorRecoveryTest(unittest.TestCase):
    def test_waits_for_ngrok_api_startup(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'local').mkdir()
            (root/'local/public-connection.json').write_text(json.dumps({'engine_origin':'https://restaurant.example/smartseat-engine'}))
            ready=Mock();ready.json.return_value={'tunnels':[{'public_url':'https://restaurant.example','config':{'addr':'http://127.0.0.1:8767'}}]}
            local=Mock(status_code=200);local.json.return_value={'app':'smartseat'}
            public=Mock(status_code=200);public.json.return_value={'app':'smartseat'}
            with patch.object(connector,'ROOT',root),patch.object(connector.requests,'get',side_effect=[requests.ConnectionError(),ready,local,public]),patch('time.sleep') as sleep:
                connector.ensure_connection()
                sleep.assert_called_once()

    def test_waits_for_new_tunnel_registration_before_verifying_public_health(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'local').mkdir()
            (root/'local/public-connection.json').write_text(json.dumps({'engine_origin':'https://restaurant.example/smartseat-engine'}))
            pending=Mock();pending.json.return_value={'tunnels':[]}
            ready=Mock();ready.json.return_value={'tunnels':[{'public_url':'https://restaurant.example','config':{'addr':'http://127.0.0.1:8767'}}]}
            local=Mock(status_code=200);local.json.return_value={'app':'smartseat'}
            public=Mock(status_code=200);public.json.return_value={'app':'smartseat'}
            with patch.object(connector,'ROOT',root),patch.object(connector.requests,'get',side_effect=[pending,ready,local,public]),patch.object(connector.requests,'post') as mutation,patch('time.sleep') as sleep:
                connector.ensure_connection()
                sleep.assert_called_once()
                mutation.assert_not_called()

    def test_configured_destination_does_not_claim_success_for_another_service(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'local').mkdir()
            (root/'local/public-connection.json').write_text(json.dumps({'engine_origin':'https://restaurant.example/smartseat-engine'}))
            tunnels=Mock();tunnels.json.return_value={'tunnels':[{'public_url':'https://restaurant.example','config':{'addr':'http://127.0.0.1:8767'}}]}
            wrong=Mock(status_code=200);wrong.json.return_value={'app':'another-service'}
            with patch.object(connector,'ROOT',root),patch.object(connector.requests,'get',side_effect=[tunnels,wrong]),patch.object(connector.requests,'post') as mutation:
                with self.assertRaisesRegex(RuntimeError,'engine and router'):
                    connector.ensure_connection()
                mutation.assert_not_called()
