"""Test-only TLS bridge. Its Docker network is internal: the public DNS name
resolves to this container, not Google Cloud. No production routing override.
"""

import http.client
import json
import ssl
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

STATE = Path("/state")
LOCK = threading.Lock()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def request(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
        if self.path == "/test/setup" and self.command == "POST":
            with LOCK:
                (STATE / "last-setup.json").write_bytes(body)
            try:
                fault = json.loads((STATE / "fault.json").read_text())
            except (FileNotFoundError, ValueError):
                fault = {}
            if fault.get("setup_status"):
                response = json.dumps(
                    {"message": "Synthetic preparation failure", "source": "system"}
                ).encode()
                self.send_response(fault["setup_status"])
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(response)))
                self.end_headers()
                self.wfile.write(response)
                return
        headers = {
            key: value
            for key, value in self.headers.items()
            if key.lower() not in {"host", "connection", "accept-encoding"}
        }
        connection = http.client.HTTPConnection("api", 8080, timeout=120)
        try:
            connection.request(self.command, self.path, body=body, headers=headers)
            upstream = connection.getresponse()
            data = upstream.read()
            self.send_response(upstream.status)
            for key, value in upstream.getheaders():
                if key.lower() not in {"connection", "transfer-encoding", "content-length"}:
                    self.send_header(key, value)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        finally:
            connection.close()

    do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = request


server = ThreadingHTTPServer(("0.0.0.0", 443), Handler)
context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
context.load_cert_chain("/tls/ca.crt", "/tls/server.key")
server.socket = context.wrap_socket(server.socket, server_side=True)
server.serve_forever()
