"""Small runnable HTTP application used to prove the delivery path."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os


def response(path):
    if path == '/healthz': return 200, {'status':'ok'}
    if path == '/': return 200, {'platform':'vCloud','service':'vcloud-api'}
    return 404, {'error':'not found'}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        status, value = response(self.path)
        payload = json.dumps(value).encode()
        self.send_response(status)
        self.send_header('Content-Type','application/json')
        self.send_header('Content-Length',str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


if __name__ == '__main__':
    ThreadingHTTPServer(('0.0.0.0',int(os.environ.get('PORT','8080'))), Handler).serve_forever()
