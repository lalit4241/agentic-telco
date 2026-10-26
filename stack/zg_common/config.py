import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = Path(os.environ.get("ZG_DATA", ROOT / ".data"))

def env(name, default):
    return os.environ.get(name, default)

PG_DSN = env("ZG_PG_DSN", "postgresql://zg@127.0.0.1:55432/agentictelco")
KAFKA_BOOTSTRAP = env("ZG_KAFKA", "127.0.0.1:9092")
KAFKA_TOPIC = "tmf688-events"
OPA_URL = env("ZG_OPA_URL", "http://127.0.0.1:8181")
OPERATON_URL = env("ZG_OPERATON_URL", "http://127.0.0.1:8180/engine-rest")
INFERENCE_URL = env("ZG_INFERENCE_URL", "http://127.0.0.1:8110")
OLLAMA_URL = env("ZG_OLLAMA_URL", "http://127.0.0.1:11434")
OLLAMA_MODEL = env("ZG_OLLAMA_MODEL", "qwen2.5:0.5b")

PORTS = {"l2_mesh": 8102, "l3_data": 8103, "l4_context": 8104, "l5_orchestrator": 8105, "l6_sor": 8106, "oss_mock": 8107,
         "network_agent": 8108, "mcp_tools": 8109, "inference": 8110, "graphql": 8111, "l6_salesforce_adapter": 8116, "l1_web": 5173}

def url(svc):
    return env("ZG_URL_" + svc.upper(), f"http://127.0.0.1:{PORTS[svc]}")

# L6 base: the stand-in by default; point at the server-side Salesforce adapter to go live.
SOR_BASE = env("ZG_SOR_BASE", url("l6_sor"))
SOR_MODE = env("ZG_SOR_MODE", "standin")  # standin | commscloud | standard-rest
