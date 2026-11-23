"""检查原件在本机来源上能被实际读取。"""
import json
from pathlib import Path
import threading
import unittest
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import urlopen

from source_server import make_server

HERE = Path(__file__).resolve().parent


class SourceTests(unittest.TestCase):
    """用 HTTP 验证读取端点和柜台实际回页。"""

    @classmethod
    def setUpClass(cls):
        cls.source = make_server()
        cls.thread = threading.Thread(target=cls.source.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f"http://127.0.0.1:{cls.source.server_port}"
        cls.config = json.loads((HERE / "origin.json").read_text(encoding="utf-8"))

    @classmethod
    def tearDownClass(cls):
        cls.source.shutdown()
        cls.thread.join()
        cls.source.server_close()

    def test_origins(self):
        for item in self.config["sources"]:
            with self.subTest(path=item), urlopen(self.url + item, timeout=3) as response:
                self.assertEqual(response.status, 200)
                raw = response.read()
                self.assertTrue(raw)
                if item.endswith(".json"):
                    self.assertIsInstance(json.loads(raw), dict)
                if item.endswith(".ndjson"):
                    self.assertTrue(all(json.loads(line) for line in raw.splitlines()))

    def test_unpublished_path(self):
        with self.assertRaises(HTTPError) as result:
            urlopen(self.url + "/unpublished", timeout=3)
        self.assertEqual(result.exception.code, 404)

    def test_forms(self):
        for form in self.config["forms"]:
            with self.subTest(path=form["path"]), urlopen(self.url + form["path"], timeout=3) as response:
                self.assertIn("<form", response.read().decode("utf-8"))
            for values, message in form["choices"]:
                query = urlencode(dict(zip(form["fields"], values, strict=True))).encode()
                with self.subTest(values=values), urlopen(self.url + form["path"], data=query, timeout=3) as response:
                    self.assertIn(message, response.read().decode("utf-8"))


if __name__ == "__main__":
    unittest.main()
