"""저장소 루트를 서비스하는 정적 서버 (Range 불필요). ?iso=1 페이지용 COOP/COEP 헤더를 항상 붙인다(교차 출처 격리 -> SharedArrayBuffer -> wasm 멀티스레드).
사용(저장소 루트에서): python3 tools/browserocr/serve.py 8765"""
import http.server, sys
class H(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        if "iso=0" not in self.path and not self.path.startswith("/tmp/"):
            self.send_header("Cross-Origin-Opener-Policy", "same-origin")
            self.send_header("Cross-Origin-Embedder-Policy", "require-corp")
        self.send_header("Cross-Origin-Resource-Policy", "cross-origin")
        self.send_header("Cache-Control", "no-store")
        super().end_headers()
    def log_message(self, *a): pass
http.server.ThreadingHTTPServer(("127.0.0.1", int(sys.argv[1]) if len(sys.argv) > 1 else 8765), H).serve_forever()
