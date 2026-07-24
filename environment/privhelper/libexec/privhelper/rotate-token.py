#!/usr/bin/env python3
import json
import os

req = json.loads(os.environ["PRIVHELPER_REQUEST"])
bind = json.loads(os.environ["PRIVHELPER_BINDING"])
out = {
    "status": "ok",
    "request_digest": bind["request_digest"],
    "manifest_generation": bind["manifest_generation"],
    "manifest_digest": bind["manifest_digest"],
    "action": req["action"],
    "unit": req["unit"],
    "effect": "token_rotated",
}
print(json.dumps(out, separators=(",", ":")))
