import json
import threading
import unittest
from urllib.request import urlopen
from app import Handler, ThreadingHTTPServer, response


class ApplicationTests(unittest.TestCase):
    def test_health(self): self.assertEqual(response('/healthz'),(200,{'status':'ok'}))
    def test_identity(self): self.assertEqual(response('/')[1]['platform'],'vCloud')
    def test_unknown_path(self): self.assertEqual(response('/private')[0],404)
    def test_real_http_response(self):
        with ThreadingHTTPServer(('127.0.0.1',0),Handler) as server:
            thread=threading.Thread(target=server.serve_forever,daemon=True)
            thread.start()
            try:
                with urlopen(f'http://127.0.0.1:{server.server_port}/healthz',timeout=2) as result:
                    self.assertEqual(json.loads(result.read()),{'status':'ok'})
                    self.assertEqual(result.headers['Content-Type'],'application/json')
            finally:
                server.shutdown()
                thread.join(timeout=2)
