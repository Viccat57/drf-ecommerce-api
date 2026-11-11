import json, os, time, pathlib, urllib.request, urllib.error

BASE = "http://garage:3903"
TOKEN = pathlib.Path("/secrets/garage/garage_admin_token").read_text().strip()
BUCKET = os.environ["GARAGE_BUCKET_NAME"]
KEY = os.environ["GARAGE_KEY_NAME"]

def api(method, path, body=None):
    req = urllib.request.Request(
        BASE + path, method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            raw = r.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise

for _ in range(60):
    try:
        status = api("GET", "/v2/GetClusterStatus")
        break
    except Exception:
        time.sleep(2)
else:
    raise SystemExit("Garage no respondió")

layout = api("GET", "/v2/GetClusterLayout")
if not layout["roles"]:
    node_id = status["nodes"][0]["id"]
    api("POST", "/v2/UpdateClusterLayout",
        {"roles": [{"id": node_id, "zone": "dc1", "capacity": 1073741824, "tags": []}]})
    api("POST", "/v2/ApplyClusterLayout", {"version": layout["version"] + 1})

bucket = api("GET", f"/v2/GetBucketInfo?globalAlias={BUCKET}") \
    or api("POST", "/v2/CreateBucket", {"globalAlias": BUCKET})

key = next((k for k in api("GET", "/v2/ListKeys") if k["name"] == KEY), None)
if key:
    key = api("GET", f"/v2/GetKeyInfo?id={key['id']}&showSecretKey=true")
else:
    key = api("POST", "/v2/CreateKey", {"name": KEY})

api("POST", "/v2/AllowBucketKey", {
    "bucketId": bucket["id"], "accessKeyId": key["accessKeyId"],
    "permissions": {"read": True, "write": True, "owner": False}})

fd = os.open("/secrets/s3/garage_s3.env", os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
with os.fdopen(fd, "w") as f:
    f.write(f"GARAGE_ACCESS_KEY_ID={key['accessKeyId']}\n"
            f"GARAGE_SECRET_ACCESS_KEY={key['secretAccessKey']}\n")