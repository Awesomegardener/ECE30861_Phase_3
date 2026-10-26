"""Disposable HTTP redirect/sentinel targets for the transport regression."""

import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

COUNT = 0
LOCK = threading.Lock()


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        with LOCK:
            data = json.dumps({"destructive_requests": COUNT}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        global COUNT
        self.rfile.read(int(self.headers.get("Content-Length", "0")))
        if os.getenv("REDIRECT_TO"):
            self.send_response(307)
            self.send_header("Location", os.environ["REDIRECT_TO"])
        else:
            with LOCK:
                COUNT += 1
            self.send_response(204)
        self.send_header("Content-Length", "0")
        self.end_headers()

    do_PUT = do_POST


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
