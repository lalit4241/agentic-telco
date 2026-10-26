"""Deterministic hashed bag-of-words embedding (64-d) stored in pgvector. Lexical, not a neural embedding – no model download
needed; swap for an embedding model served through the inference gateway in a real deployment."""
import hashlib, math, re

def embed(text, dim=64):
    v = [0.0] * dim
    for tok in re.findall(r"[a-z0-9]+", text.lower()):
        h = int(hashlib.sha256(tok.encode()).hexdigest(), 16)
        v[h % dim] += 1.0 if (h >> 8) & 1 else -1.0
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return "[" + ",".join(f"{x / n:.5f}" for x in v) + "]"
