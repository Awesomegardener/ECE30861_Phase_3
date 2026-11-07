"""Host access to internal-only contract services; destinations are fixed."""

import http.client
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def serve(port, destination):
    class Proxy(BaseHTTPRequestHandler):
        def forward(self):
            connection = http.client.HTTPConnection(destination, 8080, timeout=660)
            try:
                body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
                connection.request(self.command, self.path, body, dict(self.headers))
                response = connection.getresponse()
                data = response.read()
                self.send_response(response.status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            finally:
                connection.close()

        do_GET = do_POST = forward

        def log_message(self, *args):
            pass

    ThreadingHTTPServer(("0.0.0.0", port), Proxy).serve_forever()


for port, destination in [
    (9016, "api"),
    (9017, "tester"),
    (9018, "timeout-tester"),
    (9019, "unavailable-system"),
]:
    threading.Thread(target=serve, args=(port, destination), daemon=False).start()
