import os
import sys
import time

from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

class Handler(BaseHTTPRequestHandler):
    def do_GET(self, header_only=False):
        if self.path == "/stop":
            self.send_response(200)
            self.end_headers()
            self.server.shutdown()
            return
        if self.path == "/alive":
            self.send_response(200)
            self.end_headers()
            return
        if self.path == "/1kb":
            self.send_response(200)
            self.send_header("Content-Length", 1024)
            self.end_headers()
            if not header_only:
                self.wfile.write(os.urandom(1024))
            return
        if self.path == "/128kb":
            self.send_response(200)
            self.send_header("Content-Length", 128*1024)
            self.end_headers()
            if not header_only:
                for _ in range(128):
                    self.wfile.write(os.urandom(1024))
                    time.sleep(0.05)
            return
        if self.path == "/withauth":
            if "Authorization" not in self.headers:
                self.send_response(401)
                self.send_header("WWW-Authenticate", "Basic")
                self.end_headers()
                return
            from base64 import b64decode
            kind, _, auth = self.headers["Authorization"].partition(" ")
            resp = kind.encode() + b" " + b64decode(auth.encode("ascii"))
            self.send_response(200)
            self.send_header("Content-Length", len(resp))
            self.end_headers()
            if not header_only:
                self.wfile.write(resp)
            return
        self.send_error(404)

    def do_HEAD(self):
        return self.do_GET(header_only=True)

SERVER_ADDR = "localhost", int(sys.argv[1])
HTTPD = ThreadingHTTPServer(SERVER_ADDR, Handler)
HTTPD.serve_forever()

