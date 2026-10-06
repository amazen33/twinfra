#!/usr/bin/env python3
"""mTLS-only agent/capacity API; isolated health/metrics port contains no secrets."""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import ssl
import threading
import time
import urllib.error
import urllib.request
import uuid

from engine import Agent, CapacityEngine, CLUSTER, Ledger, Rejected, json_object


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise Rejected('Upstream redirect prohibited')


def trusted_json(url, ca_file, *, body=None, token_file=None, timeout=20, client_dir=None):
    if not url.startswith('https://'):
        raise Rejected('Upstream HTTPS required')
    headers = {'Accept': 'application/json'}
    if token_file:
        headers['Authorization'] = 'Bearer ' + Path(token_file).read_text().strip()
    data = None if body is None else json.dumps(body).encode()
    if data is not None:
        headers['Content-Type'] = 'application/json'
    context = ssl.create_default_context(cafile=ca_file)
    if client_dir:
        context.load_cert_chain(str(Path(client_dir) / 'tls.crt'), str(Path(client_dir) / 'tls.key'))
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect(), urllib.request.HTTPSHandler(context=context))
    with opener.open(urllib.request.Request(url, data=data, headers=headers), timeout=timeout) as response:
        raw = response.read(1024 * 1024 + 1)
        if len(raw) > 1024 * 1024:
            raise Rejected('Upstream response too large')
        return json_object(raw)


PLAN_SCHEMA = {'type': 'object', 'additionalProperties': False, 'required': ['action', 'answer', 'batch'],
    'properties': {'action': {'type': 'string', 'enum': ['answer', 'enqueue_simulation']},
                   'answer': {'type': ['string', 'null']}, 'batch': {'type': ['object', 'null'],
                   'additionalProperties': False, 'required': ['profile', 'nodes', 'dataset'],
                   'properties': {'profile': {'type': 'string', 'enum': ['spinifex.gpu.h100.80gb.8x']},
                                  'nodes': {'type': 'integer', 'minimum': 1, 'maximum': 4},
                                  'dataset': {'type': 'string', 'enum': ['synthetic']}}}}}


def make_agent(config):
    def model(prompt):
        response = trusted_json(config['vllm_endpoint_url'] + '/v1/chat/completions', config['vllm_ca_file'], timeout=120,
            body={'model': config['vllm_model'], 'max_tokens': config['agent_max_tokens'], 'temperature': 0.2,
                  'messages': [{'role': 'user', 'content': prompt}],
                  'response_format': {'type': 'json_schema', 'json_schema': {'name': 'vcloud_plan', 'strict': True, 'schema': PLAN_SCHEMA}}})
        return json_object(response['choices'][0]['message']['content'])
    return Agent(config, model)


QUERIES = {
    'cpu': 'min_over_time(vcloud:hpc_cpu_saturation_ratio{cluster="vCloud-prod-01"}[5m])',
    'gpu': 'min_over_time(vcloud:hpc_gpu_saturation_ratio{cluster="vCloud-prod-01"}[5m])',
    'memory': 'min_over_time(vcloud:hpc_memory_limit_ratio{cluster="vCloud-prod-01"}[5m])',
}
SOURCES = {'cpu': 'node_cpu_seconds_total{cluster="vCloud-prod-01",mode="idle"}',
           'gpu': 'DCGM_FI_DEV_GPU_UTIL{cluster="vCloud-prod-01"}',
           'memory': 'container_memory_working_set_bytes{cluster="vCloud-prod-01",namespace="hpc-compute",container!="",container!="POD"}'}
for name in QUERIES:
    recording = 'vcloud:hpc_' + ('memory_limit' if name == 'memory' else name + '_saturation') + '_ratio'
    QUERIES[name] += (f' and on(cluster) (count_over_time({recording}{{cluster="vCloud-prod-01"}}[5m]) >= 10)'
                      f' and on(cluster) (max by(cluster) (time() - timestamp({SOURCES[name]})) < 60)')


def pending_requests(config):
    from urllib.parse import urlencode
    data = trusted_json(config['api_server_url'] + '/apis/kueue.x-k8s.io/v1beta2/namespaces/hpc-compute/workloads?' +
                        urlencode({'labelSelector': 'vcloud.io/offload-target=spinifex-hpc', 'limit': 100}),
                        '/var/run/vcloud/kubernetes/ca.crt', token_file='/var/run/vcloud/kubernetes/token')
    for workload in data['items']:
        conditions = {c['type']: c['status'] for c in workload.get('status', {}).get('conditions', [])}
        if (conditions.get('QuotaReserved') == 'True' and conditions.get('Admitted') != 'True' and
                conditions.get('Finished') != 'True' and workload['spec']['queueName'] == config['queue']):
            yield dict(request_id=str(uuid.uuid5(uuid.NAMESPACE_URL, 'vcloud:' + workload['metadata']['uid'])),
                       workload_name=workload['metadata']['name'], workload_uid=workload['metadata']['uid'],
                       profile=config['default_profile'], nodes=sum(p['count'] for p in workload['spec']['podSets']), queue=config['queue'])


def alert_candidate(payload):
    return payload.get('status') == 'firing' and any(
        alert.get('status') == 'firing' and alert.get('labels', {}).get('alertname') == 'VCloudHPCBurstCandidate' and
        alert['labels'].get('cluster') == CLUSTER and alert['labels'].get('queue') == 'spinifex-hpc-burst'
        for alert in payload.get('alerts', []))


def make_capacity(config):
    token = '/var/run/vcloud/kubernetes/token'
    def workload(request):
        return trusted_json(config['api_server_url'] + '/apis/kueue.x-k8s.io/v1beta2/namespaces/hpc-compute/workloads/' + request['workload_name'],
                            '/var/run/vcloud/kubernetes/ca.crt', token_file=token)
    def metrics():
        from urllib.parse import urlencode
        result = {}
        # An Alertmanager body is only a wake-up signal. Always refetch samples
        # from the accepted metrics backend, and reject partial/ambiguous vectors.
        for name, query in QUERIES.items():
            data = trusted_json(config['prometheus_url'] + '/api/v1/query?' + urlencode({'query': query}),
                                config['prometheus_ca_file'], client_dir='/var/run/vcloud/prometheus')
            if data['status'] != 'success' or data['data']['resultType'] != 'vector' or len(data['data']['result']) != 1:
                raise Rejected('Missing or ambiguous trusted metrics')
            sample = data['data']['result'][0]
            if sample['metric'].get('cluster') != CLUSTER:
                raise Rejected('Unexpected metrics cluster')
            result[name] = dict(cluster=CLUSTER, value=float(sample['value'][1]), timestamp=sample['value'][0], window_seconds=300)
        return result
    return CapacityEngine(config, lambda: Ledger('/var/lib/vcloud/capacity.db'), workload, metrics)


def peer_allowed(cert, expected):
    identities = {value for kind, value in cert.get('subjectAltName', []) if kind == 'URI'}
    return len(identities) == 1 and identities <= set(expected)


class MTLSServer(ThreadingHTTPServer):
    """Bound concurrent connections and run TLS handshakes in worker threads."""
    daemon_threads = True
    def __init__(self, address, handler, context):
        self.context = context
        self.connections = threading.BoundedSemaphore(16)
        super().__init__(address, handler)

    def process_request(self, request, address):
        if not self.connections.acquire(blocking=False):
            self.shutdown_request(request); return
        try: super().process_request(request, address)
        except Exception:
            self.connections.release(); self.shutdown_request(request)

    def process_request_thread(self, request, address):
        connection = request
        try:
            request.settimeout(10)
            connection = self.context.wrap_socket(request, server_side=True)
            connection.settimeout(15)
            self.finish_request(connection, address)
        except Exception:
            pass # Never log peer certificates, tokens or request payloads.
        finally:
            self.shutdown_request(connection); self.connections.release()


def service(config, mode):
    engine = make_agent(config) if mode == 'agent' else make_capacity(config)
    allowed = ['spiffe://vcloud/platform/apisix'] if mode == 'agent' else [
        'spiffe://vcloud/hpc/tekton-trigger', 'spiffe://vcloud/platform/alertmanager']
    semaphore = threading.BoundedSemaphore(16)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass # Request paths, payloads, model output and credentials stay out of logs.

        def reply(self, code, data):
            raw = json.dumps(data).encode()
            self.send_response(code); self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(raw))); self.end_headers(); self.wfile.write(raw)

        def do_POST(self):
            self.connection.settimeout(15)
            if not peer_allowed(self.connection.getpeercert(), allowed):
                self.reply(403, {'error': 'unauthorized workload identity'}); return
            if not semaphore.acquire(blocking=False):
                self.reply(503, {'error': 'request capacity exceeded'}); return
            try:
                if self.path not in (['/v1/agent/runs'] if mode == 'agent' else ['/hooks/capacity', '/hooks/alerts']):
                    self.reply(404, {'error': 'unknown endpoint'}); return
                if self.headers.get('Transfer-Encoding') or self.headers.get('Content-Type') != 'application/json':
                    raise Rejected('Only bounded JSON requests are accepted')
                if len(self.headers.get_all('Content-Length', [])) != 1:
                    raise Rejected('Exactly one body length required')
                length = int(self.headers.get('Content-Length', '0'))
                if not 1 <= length <= 65536:
                    raise Rejected('Request body limit exceeded')
                payload = json_object(self.rfile.read(length))
                if mode == 'agent':
                    result = engine.run(payload)
                elif self.path == '/hooks/alerts':
                    if not config['offload_enabled']:
                        result = {'status': 'disabled', 'offload_enabled': False}
                    elif not alert_candidate(payload):
                        result = {'status': 'ignored'}
                    else:
                        result = {'decisions': [engine.handle(request) for request in list(pending_requests(config))[:1]]}
                else:
                    result = engine.handle(payload)
                self.reply(200 if mode == 'agent' else 202, result)
            except (Rejected, ValueError, KeyError, TypeError):
                self.reply(422, {'error': 'request or prerequisite rejected'})
            except Exception:
                self.reply(503, {'error': 'dependency unavailable; no unsafe fallback'})
            finally:
                semaphore.release()

    Handler.engine = engine
    return Handler


def config_from_files(path):
    config = json_object(Path(path).read_text())
    if 'SPINIFEX_OFFLOAD_ENABLED' in os.environ:
        value = os.environ['SPINIFEX_OFFLOAD_ENABLED']
        if value not in ('true', 'false'):
            raise Rejected('Invalid feature flag')
        config['offload_enabled'] = value == 'true'
    config['endpoint_url'] = os.environ.get('SPINIFEX_ENDPOINT_URL', config['endpoint_url'])
    config['default_profile'] = os.environ.get('SPINIFEX_GPU_PROFILE', config['default_profile'])
    config['max_burst_nodes'] = int(os.environ.get('SPINIFEX_MAX_BURST_NODES', config['max_burst_nodes']))
    return config


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--mode', choices=['agent', 'capacity'], required=True)
    parser.add_argument('--config', default='/etc/vcloud/reference-profile.json')
    args = parser.parse_args(); config = config_from_files(args.config)
    handler = service(config, args.mode)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER); context.minimum_version = ssl.TLSVersion.TLSv1_3
    context.verify_mode = ssl.CERT_REQUIRED
    context.load_cert_chain('/var/run/vcloud/tls/tls.crt', '/var/run/vcloud/tls/tls.key')
    context.load_verify_locations('/var/run/vcloud/tls/ca.crt')
    server = MTLSServer(('0.0.0.0', 8443), handler, context)
    reconciliation = {'failures': 0, 'uncertain': 0, 'expired': 0}
    class Health(BaseHTTPRequestHandler):
        def log_message(self, *_): pass
        def do_GET(self):
            body = b'ok\n' if self.path == '/healthz' else (
                ('# TYPE vcloud_spinifex_offload_enabled gauge\nvcloud_spinifex_offload_enabled ' +
                 str(int(config['offload_enabled'])) + '\n' +
                 ''.join('vcloud_spinifex_reconciliation_' + key + ' ' + str(value) + '\n' for key, value in reconciliation.items())).encode() if self.path == '/metrics' else None)
            if body is None: self.send_error(404); return
            self.send_response(200); self.end_headers(); self.wfile.write(body)
    health = ThreadingHTTPServer(('0.0.0.0', 9091), Health)
    threading.Thread(target=health.serve_forever, daemon=True).start()
    if args.mode == 'capacity':
        def reconcile_loop():
            while True:
                time.sleep(60)
                try:
                    states = handler.engine.reconcile()
                    reconciliation['uncertain'] = sum(s['state'] == 'uncertain' for s in states)
                    reconciliation['expired'] = sum(s.get('expired', False) for s in states)
                except Exception:
                    reconciliation['failures'] += 1
        threading.Thread(target=reconcile_loop, daemon=True).start()
    server.serve_forever()


if __name__ == '__main__':
    main()
