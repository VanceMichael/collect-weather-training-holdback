"""在本机提供资料方的合成网页、回执和原件。"""
import argparse
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import re
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

HERE = Path(__file__).resolve().parent

_TYPES = {
    ".csv": "text/csv", ".json": "application/json", ".ndjson": "application/x-ndjson",
    ".html": "text/html", ".txt": "text/plain", ".vtt": "text/vtt",
}


def _html(title, body):
    return (
        '<!doctype html><html lang="zh"><head><meta charset="utf-8">'
        f'<title>{escape(title)}</title></head><body><h1>{escape(title)}</h1>{body}</body></html>'
    )


def _inputs(path, fields):
    rows = "".join(f'<p><label>{escape(label)} <input name="{escape(field)}" required></label></p>'
                   for field, label in fields.items())
    return f'<form method="post" action="{escape(path)}">{rows}<button>办理</button></form>'


class Desk(BaseHTTPRequestHandler):
    """外部资料站与柜台的本机替代服务。"""

    def _response(self, code, mime, contents, headers=()):
        payload = contents if isinstance(contents, bytes) else contents.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", f"{mime}; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        for name, value in headers:
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(payload)

    def _document(self, path):
        payload = self.server.sources[path].read_bytes()
        mime = _TYPES[Path(path).suffix]
        value = self.headers.get("Range")
        if not value or path not in self.server.range_sources:
            self._response(200, mime, payload)
            return
        match = re.fullmatch(r"bytes=(\d+)-(\d*)", value)
        if not match:
            self._response(416, "text/plain", "不支持的范围", [("Content-Range", f"bytes */{len(payload)}")])
            return
        start = int(match[1])
        end = min(int(match[2]), len(payload) - 1) if match[2] else len(payload) - 1
        if not 0 <= start <= end:
            self._response(416, "text/plain", "所求范围尚不可用", [("Content-Range", f"bytes */{len(payload)}")])
            return
        headers = [("Accept-Ranges", "bytes"), ("Content-Range", f"bytes {start}-{end}/{len(payload)}")]
        self._response(206, mime, payload[start:end + 1], headers)

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == "/":
            links = "".join(f'<li><a href="{escape(key)}">{escape(key)}</a></li>'
                            for key in [*self.server.sources, *self.server.forms])
            self._response(200, "text/html", _html(self.server.title, f"<ul>{links}</ul>"))
        elif path in self.server.forms:
            record = self.server.forms[path]
            form = _inputs(path, record["fields"])
            self._response(200, "text/html", _html(record["title"], form))
        elif path in self.server.sources:
            self._document(path)
        else:
            self._response(404, "text/plain", "资料未公布")

    def do_POST(self):
        path = urlsplit(self.path).path
        record = self.server.forms.get(path)
        if not record:
            self._response(404, "text/plain", "柜台不存在")
            return
        if self.headers.get_content_type() != "application/x-www-form-urlencoded":
            self._response(415, "text/plain", "此柜台接收页面表单")
            return
        size = int(self.headers.get("Content-Length", 0))
        if not 0 < size <= 16_384:
            self._response(400, "text/plain", "表单长度无效")
            return
        values = parse_qs(self.rfile.read(size).decode("utf-8"), keep_blank_values=True)
        keys = tuple(values.get(name, [""])[0] for name in record["fields"])
        receipt = next((body for lookup, body in record["choices"] if tuple(lookup) == keys), None)
        status = 200 if receipt is not None else 404
        body = escape(receipt) if receipt is not None else "柜台未找到所填资料"
        self._response(status, "text/html", _html(record["title"], f'<output>{body}</output>'))


def make_server(port=0, host="127.0.0.1"):
    conf = json.loads((HERE / "origin.json").read_text(encoding="utf-8"))
    server = ThreadingHTTPServer((host, port), Desk)
    server.title = conf["title"]
    server.sources = {key: HERE / "origins" / key.lstrip("/") for key in conf["sources"]}
    server.forms = {form["path"]: form for form in conf["forms"]}
    server.range_sources = set(conf.get("range_sources", []))
    return server


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="运行本机资料站")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8040, type=int)
    args = parser.parse_args()
    with make_server(args.port, args.host) as server:
        print(f"资料站 http://{args.host}:{args.port}/", flush=True)
        server.serve_forever()
