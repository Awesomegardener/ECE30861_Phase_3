"""Deliberately wrong isolated HTTP target, solely for report verification."""

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length", "0")))
        if self.path == "/api/v1/test/reset":
            self.send_response(204)
            self.end_headers()
        else:
            self.reply({"deliberately": "invalid release response"})

    def do_PUT(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
        self.reply(json.loads(body) if self.path == "/api/v1/test/clock" else {})

    def do_GET(self):
        self.reply({})

    def reply(self, body):
        data = json.dumps(body).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
