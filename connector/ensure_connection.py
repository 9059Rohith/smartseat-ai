"""Restore the dedicated path through the running local connector, preserving its other routes."""
import json
from pathlib import Path
import time
from urllib.parse import urlparse
import requests

ROOT = Path(__file__).resolve().parents[1]

def ensure_connection():
    config = json.loads((ROOT / 'local/public-connection.json').read_text())
    origin = urlparse(config['engine_origin'])
    if origin.scheme != 'https' or origin.path.rstrip('/') != '/smartseat-engine':
        raise RuntimeError('Expected the dedicated HTTPS SmartSeat connector path.')
    api = 'http://127.0.0.1:4040/api'
    matches = []
    for attempt in range(20):
        try:
            tunnels = requests.get(api + '/tunnels', timeout=2).json()['tunnels']
        except requests.RequestException as error:
            if attempt == 19:
                raise RuntimeError('The ngrok local API did not become available.') from error
            time.sleep(.5)
            continue
        matches = [t for t in tunnels if urlparse(t['public_url']).netloc == origin.netloc]
        if matches:
            break
        if attempt < 19:
            time.sleep(.5)
    if len(matches) != 1:
        raise RuntimeError('The expected ngrok endpoint is missing or ambiguous. No connector was changed.')
    tunnel = matches[0]
    current = tunnel['config']['addr']
    health = requests.get('http://127.0.0.1:8767/smartseat-engine/api/health', timeout=10)
    if health.status_code != 200 or health.json().get('app') != 'smartseat':
        raise RuntimeError('Start the dedicated SmartSeat engine and router first.')
    if current == 'http://127.0.0.1:8767':
        public = requests.get(config['engine_origin'] + '/api/health', headers={'ngrok-skip-browser-warning':'true'}, timeout=20)
        if public.status_code != 200 or public.json().get('app') != 'smartseat':
            raise RuntimeError('The public restaurant engine health check failed.')
        print('SmartSeat connector is configured and healthy.'); return
    if current != 'http://127.0.0.1:8765':
        raise RuntimeError('The connector has an unexpected destination. It was left unchanged.')
    body = {'name': tunnel['name'], 'proto': 'http', 'addr': current, 'domain': origin.netloc,
            'inspect': tunnel['config']['inspect']}
    (ROOT / 'local/connector-tunnel-backup.json').write_text(json.dumps(body), encoding='utf-8')
    endpoint = api + '/tunnels/' + tunnel['name']
    requests.delete(endpoint, timeout=10).raise_for_status()
    try:
        requests.post(api + '/tunnels', json={**body, 'addr': 'http://127.0.0.1:8767'}, timeout=20).raise_for_status()
        result = requests.get(config['engine_origin'] + '/api/health', headers={'ngrok-skip-browser-warning':'true'}, timeout=20)
        if result.status_code != 200 or result.json().get('app') != 'smartseat':
            raise RuntimeError('The public restaurant engine health check failed.')
    except Exception:
        requests.delete(endpoint, timeout=10)
        requests.post(api + '/tunnels', json=body, timeout=20).raise_for_status()
        raise
    print('SmartSeat routing restored. Existing application routes are preserved.')

if __name__ == '__main__':
    ensure_connection()
