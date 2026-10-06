"""Small non-root function example; no directory listing or arbitrary file lookup."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/healthz':
            body, code = b'ok\n', 200
        elif self.path == '/':
            try:
                with Path('/data/greeting.txt').open('rb') as stream:
                    body, code = stream.read(4096), 200
            except OSError:
                body, code = b'function data not available\n', 503
        else:
            body, code = b'not found\n', 404
        self.send_response(code)
        self.send_header('Content-Type', 'text/plain; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_):
        pass # Never log tokens, request headers or untrusted URL payloads.


if __name__ == '__main__':
    ThreadingHTTPServer(('0.0.0.0', 8080), Handler).serve_forever()
