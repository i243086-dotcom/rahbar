"""Deterministic Ollama-compatible embedding double for CI fixture retrieval."""

import hashlib
import json
import math
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MODEL = "fixture-lexical-v1"
DIMENSION = 2048
STOP = set(("a an the is are be can to in of for on at do i my and or what when how "
            "much does this that it have must with say if now had from").split())


def embed(text: str) -> list[float]:
    words = re.findall(r"[a-z]+|\d[\d,.]*", text.lower())
    tokens = {
        "attend" if word in {"attendance", "attend"} else
        word.rstrip("s") if len(word) > 4 else word
        for word in words if word not in STOP
    }
    vector = [0.0] * DIMENSION
    for token in tokens:
        digest = hashlib.blake2s(token.encode(), digest_size=4).digest()
        vector[int.from_bytes(digest, "big") % DIMENSION] += 1
    norm = math.hypot(*vector)
    return [value / norm for value in vector] if norm else vector


class Handler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        if self.path != "/api/embed":
            self.send_error(404)
            return
        request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if request["model"] != MODEL:
            self.send_error(400, "unsupported embedding model")
            return
        texts = request["input"]
        if isinstance(texts, str):
            texts = [texts]
        body = json.dumps({"model": MODEL, "embeddings": [embed(text) for text in texts]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 11434), Handler).serve_forever()
