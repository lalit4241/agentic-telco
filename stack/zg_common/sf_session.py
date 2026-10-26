"""Server-side calls to the Salesforce org through the Salesforce CLI (`sf api request rest --target-org <alias>`).

Salesforce CLI 2.155 redacts the access token in `sf org display`, so this module never handles a token at all: the
CLI signs each request with its own stored session. Nothing here logs, records, writes or returns a credential, and
nothing here is reachable from the browser. Alias: $SF_TARGET_ORG (default sfcomms)."""
import json, os, re, subprocess, tempfile, time

ALIAS = os.environ.get("SF_TARGET_ORG", "sfcomms")
API_V = "v" + os.environ.get("SF_API_VERSION", "68.0").lstrip("v")

class SfResponse:
    def __init__(self, status, headers, text):
        self.status_code, self.headers, self.text = status, headers, text
    def json(self):
        try:
            return json.loads(self.text) if self.text.strip() else None
        except ValueError:
            return {"raw": self.text[:2000]}

def request(method: str, path: str, body=None, alias: str | None = None, timeout: int = 90) -> SfResponse:
    if not path.startswith("/services/"):
        raise ValueError("only /services/... paths")
    if method.upper() == "DELETE":
        raise PermissionError("AgenticTelco never deletes org records")
    cmd = ["sf", "api", "request", "rest", path, "--target-org", alias or ALIAS, "-X", method.upper(), "-i",
           "-H", "Content-Type:application/json", "-H", "Accept:application/json"]
    tmp = None
    if body is not None:
        tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
        json.dump(body, tmp); tmp.close()
        cmd += ["-b", "@" + tmp.name]
    try:
        attempts = 4 if method.upper() == "GET" else 1   # never blindly retry a write
        for n in range(attempts):
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            out = proc.stdout
            if out.startswith("HTTP/"):
                break
            time.sleep(1.5 * (n + 1))
        if not out.startswith("HTTP/"):
            return SfResponse(0, {}, json.dumps({"cliError": (proc.stderr or "")[-400:]}))
    finally:
        if tmp:
            os.unlink(tmp.name)
    all_lines = out.split("\n")
    i = 1
    while i < len(all_lines) and re.match(r"^[A-Za-z0-9-]+: ", all_lines[i]):
        i += 1
    lines, rest = all_lines[:i], "\n".join(all_lines[i:]).strip()
    status = int(lines[0].split()[1]) if lines and lines[0].startswith("HTTP/") else 0
    headers = {l.split(":", 1)[0].lower(): l.split(":", 1)[1].strip() for l in lines[1:] if ":" in l}
    return SfResponse(status, headers, rest)
