"""CPU-only Knative demo; sends a real OTLP/HTTP span for each request."""
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
import secrets
import time
import urllib.request

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        start=time.time_ns()
        body=b'vcloud-knative-cpu-ok\n'
        self.send_response(200);self.send_header('Content-Type','text/plain');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
        span={'traceId':secrets.token_hex(16),'spanId':secrets.token_hex(8),'name':'vcloud-demo-request','kind':2,
              'startTimeUnixNano':str(start),'endTimeUnixNano':str(time.time_ns()),'status':{'code':1}}
        payload={'resourceSpans':[{'resource':{'attributes':[{'key':'service.name','value':{'stringValue':'demo-cpu-app'}}]},
                                  'scopeSpans':[{'scope':{'name':'vcloud-local-acceptance'},'spans':[span]}]}]}
        request=urllib.request.Request('http://otel-collector.platform-services.svc.cluster.local:4318/v1/traces',
                                       data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'})
        try:
            with urllib.request.urlopen(request,timeout=2) as response:response.read()
            print('OTLP span exported for demo-cpu-app',flush=True)
        except Exception:print('OTLP export failed',flush=True)
    def log_message(self,*args):pass

ThreadingHTTPServer(('0.0.0.0',8080),Handler).serve_forever()
