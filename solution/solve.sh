#!/bin/bash
set -euo pipefail

change=/app/change
ris=$change/ris
decisions=$change/decisions

policy_value() {
  local file=$1 key=$2
  awk -F= -v wanted="$key" '$1 == wanted {print substr($0, index($0, "=") + 1)}' "$file"
}

sha() {
  sha256sum "$1" | cut -d' ' -f1
}

change_id=$(policy_value /app/policy/maintenance/window.conf change_id)
router=$(policy_value /app/policy/maintenance/window.conf router)
approved_profile=$(policy_value /app/policy/maintenance/window.conf profile)
ipv4_resource=$(policy_value /app/policy/visibility.conf ipv4_resource)
ipv6_resource=$(policy_value /app/policy/visibility.conf ipv6_resource)
acquisition_id=$(python3 -c 'import uuid; print(uuid.uuid4())')
endpoint=https://stat.ripe.net/data/routing-status/data.json
user_agent="$router-change/$change_id"
session_started=$(python3 -c 'from datetime import datetime, timezone; print(datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"))')

rm -rf "$change"
install -d -m 0750 "$change" "$ris" "$ris/01" "$ris/02" "$ris/03" "$decisions"
install -m 0640 /app/etc/frr/running.conf "$change/rollback.conf"
cmp -s /app/etc/frr/running.conf "$change/rollback.conf"

python3 - "$change/session.json" "$acquisition_id" "$change_id" "$router" \
  "$endpoint" "$user_agent" "$session_started" <<'PY'
import hashlib
import json
import pathlib
import sys

output, acquisition_id, change_id, router, endpoint, agent, started = sys.argv[1:]
value = {
    "acquisition_id": acquisition_id,
    "change_id": change_id,
    "router": router,
    "endpoint": endpoint,
    "user_agent": agent,
    "started_at": started,
    "policy_sha256": hashlib.sha256(
        pathlib.Path("/app/policy/visibility.conf").read_bytes()
    ).hexdigest(),
}
pathlib.Path(output).write_text(json.dumps(value, indent=2) + "\n")
PY
chmod 0640 "$change/session.json"

previous_request=$(printf '0%.0s' {1..64})

fetch() {
  local round=$1 family=$2 resource=$3 sequence=$4 body_tmp header_tmp metrics_tmp
  local started_at completed_at requested_url
  body_tmp=$(mktemp "$ris/$round/.${family}.body.XXXXXX")
  header_tmp=$(mktemp "$ris/$round/.${family}.headers.XXXXXX")
  metrics_tmp=$(mktemp "$ris/$round/.${family}.metrics.XXXXXX")
  trap 'rm -f "$body_tmp" "$header_tmp" "$metrics_tmp"' RETURN
  started_at=$(python3 -c 'from datetime import datetime, timezone; print(datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"))')
  requested_url=$(python3 - "$resource" <<'PY'
import sys
import urllib.parse
print("https://stat.ripe.net/data/routing-status/data.json?resource=" +
      urllib.parse.quote(sys.argv[1], safe=""))
PY
)
  python3 - "$ris/$round/$family.request.json" "$acquisition_id" "$sequence" \
    "$round" "$family" "$resource" "$requested_url" "$user_agent" \
    "$(sha "$change/session.json")" "$previous_request" <<'PY'
import hashlib
import json
import pathlib
import sys

(output, acquisition_id, sequence, round_id, family, resource, url, agent,
 session_sha256, previous) = sys.argv[1:]
value = {
    "acquisition_id": acquisition_id,
    "sequence": int(sequence),
    "round": round_id,
    "family": family,
    "resource": resource,
    "url": url,
    "user_agent": agent,
    "session_sha256": session_sha256,
    "previous_request_sha256": previous,
}
canonical = json.dumps(value, separators=(",", ":"), ensure_ascii=False).encode()
value["request_sha256"] = hashlib.sha256(
    b"RIS-REQUEST-V2\0" + canonical
).hexdigest()
pathlib.Path(output).write_text(
    json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
)
PY
  chmod 0640 "$ris/$round/$family.request.json"
  previous_request=$(jq -r .request_sha256 "$ris/$round/$family.request.json")
  curl --fail --silent --show-error --location --max-redirs 3 \
    --http1.1 \
    --connect-timeout 20 --max-time 90 \
    --retry 3 --retry-all-errors --retry-delay 2 \
    --suppress-connect-headers \
    --user-agent "$user_agent" \
    --get --data-urlencode "resource=$resource" \
    --dump-header "$header_tmp" --output "$body_tmp" \
    --write-out '%{url_effective}\n%{response_code}\n%{content_type}\n%{remote_ip}\n%{ssl_verify_result}\n%{http_version}\n%{num_redirects}\n%{size_download}\n%{time_total}\n' \
    'https://stat.ripe.net/data/routing-status/data.json' >"$metrics_tmp"
  completed_at=$(python3 -c 'from datetime import datetime, timezone; print(datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"))')
  python3 - "$header_tmp" <<'PY'
import email.parser
import pathlib
import re
import sys

path = pathlib.Path(sys.argv[1])
raw = path.read_bytes()
starts = [match.start() for match in re.finditer(br"(?m)^HTTP/", raw)]
if not starts:
    raise SystemExit("response did not contain an HTTP header block")
raw = raw[starts[-1]:]
if not raw.endswith((b"\r\n\r\n", b"\n\n")):
    raise SystemExit("final HTTP header block was incomplete")
path.write_bytes(raw)
headers = email.parser.BytesHeaderParser().parsebytes(
    b"".join(raw.splitlines(keepends=True)[1:])
)
if not headers.get("Date"):
    raise SystemExit("response headers are missing Date")
if not headers.get("Content-Type", "").lower().startswith("application/json"):
    raise SystemExit("response content type is not JSON")
PY
  python3 - "$metrics_tmp" "$header_tmp" "$body_tmp" \
    "$ris/$round/$family.meta.json" "$acquisition_id" "$sequence" "$round" \
    "$family" "$requested_url" "$started_at" "$completed_at" \
    "$ris/$round/$family.request.json" <<'PY'
import hashlib
import json
import pathlib
import sys

(metrics_path, headers_path, body_path, output_path, acquisition_id, sequence,
 round_id, family, requested_url, started_at, completed_at,
 request_path) = sys.argv[1:]
values = pathlib.Path(metrics_path).read_text().splitlines()
if len(values) != 9:
    raise SystemExit("incomplete curl transfer metadata")
(effective_url, status, content_type, remote_ip, tls_result, http_version,
 redirects, size_download, time_total) = values
headers = pathlib.Path(headers_path).read_bytes()
body = pathlib.Path(body_path).read_bytes()
payload = json.loads(body)
semantic = json.dumps(
    payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")
).encode()
request = json.loads(pathlib.Path(request_path).read_bytes())
if int(size_download) != len(body):
    raise SystemExit("curl byte count mismatch")
value = {
    "acquisition_id": acquisition_id,
    "sequence": int(sequence),
    "round": round_id,
    "family": family,
    "requested_url": requested_url,
    "effective_url": effective_url,
    "started_at": started_at,
    "completed_at": completed_at,
    "status_code": int(status),
    "content_type": content_type,
    "remote_ip": remote_ip,
    "tls_verified": tls_result == "0",
    "http_version": http_version,
    "redirects": int(redirects),
    "bytes_downloaded": len(body),
    "duration_ms": round(float(time_total) * 1000),
    "request_sha256": request["request_sha256"],
    "headers_sha256": hashlib.sha256(headers).hexdigest(),
    "body_sha256": hashlib.sha256(body).hexdigest(),
    "semantic_sha256": hashlib.sha256(
        b"RIS-JSON-SEMANTIC-V1\0" + semantic
    ).hexdigest(),
}
if not value["tls_verified"]:
    raise SystemExit("TLS verification failed")
pathlib.Path(output_path).write_text(
    json.dumps(value, indent=2) + "\n", encoding="utf-8"
)
PY
  chmod 0640 "$body_tmp" "$header_tmp" "$ris/$round/$family.meta.json"
  mv -fT "$body_tmp" "$ris/$round/$family.json"
  mv -fT "$header_tmp" "$ris/$round/$family.headers"
  rm -f "$metrics_tmp"
  trap - RETURN
}

sequence=0
for round in 01 02 03; do
  ((sequence+=1))
  fetch "$round" ipv4 "$ipv4_resource" "$sequence"
  ((sequence+=1))
  fetch "$round" ipv6 "$ipv6_resource" "$sequence"
done

python3 - "$ris" <<'PY'
import email.parser
import email.utils
import json
import pathlib
import sys
from datetime import datetime, timedelta, timezone

root = pathlib.Path(sys.argv[1])
now = datetime.now(timezone.utc)
dates = {}
previous_completion = None
for round_id in ("01", "02", "03"):
    for family in ("ipv4", "ipv6"):
        raw = (root / round_id / f"{family}.headers").read_bytes()
        headers = email.parser.BytesHeaderParser().parsebytes(
            b"".join(raw.splitlines(keepends=True)[1:])
        )
        fetched = email.utils.parsedate_to_datetime(headers["Date"]).astimezone(
            timezone.utc
        )
        payload = json.loads((root / round_id / f"{family}.json").read_bytes())
        metadata = json.loads(
            (root / round_id / f"{family}.meta.json").read_bytes()
        )
        started = datetime.fromisoformat(metadata["started_at"].replace("Z", "+00:00"))
        completed = datetime.fromisoformat(metadata["completed_at"].replace("Z", "+00:00"))
        queried = datetime.fromisoformat(
            payload["data"]["query_time"].replace("Z", "+00:00")
        ).astimezone(timezone.utc)
        if abs((now - fetched).total_seconds()) > 45 * 60:
            raise SystemExit(f"{round_id}/{family} HTTP Date is stale")
        if queried > fetched or (fetched - queried).total_seconds() > 12 * 60 * 60:
            raise SystemExit(f"{round_id}/{family} query_time outside window")
        if completed < started or (
            previous_completion is not None and started < previous_completion
        ):
            raise SystemExit(f"{round_id}/{family} client chronology is invalid")
        if fetched < started.replace(microsecond=0) - timedelta(minutes=5) or \
           fetched > completed.replace(microsecond=0) + timedelta(minutes=5):
            raise SystemExit(f"{round_id}/{family} HTTP Date conflicts with client time")
        previous_completion = completed
        dates[round_id, family] = fetched
for round_id in ("01", "02", "03"):
    if dates[round_id, "ipv6"] < dates[round_id, "ipv4"]:
        raise SystemExit(f"round {round_id} acquisition order is invalid")
for family in ("ipv4", "ipv6"):
    if not (
        dates["01", family]
        <= dates["02", family]
        <= dates["03", family]
    ):
        raise SystemExit(f"{family} round chronology is invalid")
if (dates["03", "ipv6"] - dates["01", "ipv4"]).total_seconds() > 20 * 60:
    raise SystemExit("acquisition span exceeds 20 minutes")
PY

python3 - "$ris" "$change/acquisition.jsonl" "$ipv4_resource" "$ipv6_resource" <<'PY'
import email.parser
import hashlib
import json
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
output = pathlib.Path(sys.argv[2])
resources = {"ipv4": sys.argv[3], "ipv6": sys.argv[4]}
previous = "0" * 64
lines = []
sequence = 0
for round_id in ("01", "02", "03"):
    for family in ("ipv4", "ipv6"):
        sequence += 1
        headers_path = root / round_id / f"{family}.headers"
        body_path = root / round_id / f"{family}.json"
        metadata_path = root / round_id / f"{family}.meta.json"
        request_path = root / round_id / f"{family}.request.json"
        header_bytes = headers_path.read_bytes()
        body_bytes = body_path.read_bytes()
        metadata_bytes = metadata_path.read_bytes()
        metadata = json.loads(metadata_bytes)
        request = json.loads(request_path.read_bytes())
        headers = email.parser.BytesHeaderParser().parsebytes(
            b"".join(header_bytes.splitlines(keepends=True)[1:])
        )
        payload = json.loads(body_bytes)
        entry = {
            "acquisition_id": metadata["acquisition_id"],
            "sequence": sequence,
            "round": round_id,
            "family": family,
            "resource": resources[family],
            "http_date": headers["Date"],
            "query_time": payload["data"]["query_time"],
            "request_sha256": request["request_sha256"],
            "metadata_sha256": hashlib.sha256(metadata_bytes).hexdigest(),
            "headers_sha256": hashlib.sha256(header_bytes).hexdigest(),
            "body_sha256": hashlib.sha256(body_bytes).hexdigest(),
            "semantic_sha256": metadata["semantic_sha256"],
            "previous_sha256": previous,
        }
        canonical = json.dumps(
            entry, ensure_ascii=False, separators=(",", ":")
        ).encode()
        previous = hashlib.sha256(b"RIS-ACQUISITION-V1\0" + canonical).hexdigest()
        entry["entry_sha256"] = previous
        lines.append(
            json.dumps(entry, ensure_ascii=False, separators=(",", ":"))
        )
output.write_text("\n".join(lines) + "\n", encoding="utf-8")
PY
chmod 0640 "$change/acquisition.jsonl"

python3 - "$ris" "$change/session.json" "$change/acquisition.jsonl" \
  "$change/acquisition-checkpoints.jsonl" <<'PY'
import hashlib
import json
import pathlib
import sys

ris, session_path, acquisition_path, output = map(pathlib.Path, sys.argv[1:])
acquisition = [
    json.loads(line) for line in acquisition_path.read_text().splitlines()
]
previous = "0" * 64
records = []
for round_number, round_id in enumerate(("01", "02", "03"), start=1):
    digest = hashlib.sha256(b"RIS-ROUND-EVIDENCE-V1\0")
    for family in ("ipv4", "ipv6"):
        for suffix in ("request.json", "headers", "json", "meta.json"):
            digest.update(hashlib.sha256(
                (ris / round_id / f"{family}.{suffix}").read_bytes()
            ).digest())
    value = {
        "round": round_id,
        "last_sequence": round_number * 2,
        "round_evidence_sha256": digest.hexdigest(),
        "request_tail_sha256": json.loads(
            (ris / round_id / "ipv6.request.json").read_bytes()
        )["request_sha256"],
        "session_sha256": hashlib.sha256(session_path.read_bytes()).hexdigest(),
        "acquisition_tail_sha256": acquisition[round_number * 2 - 1][
            "entry_sha256"
        ],
        "previous_sha256": previous,
    }
    canonical = json.dumps(value, separators=(",", ":")).encode()
    previous = hashlib.sha256(
        b"RIS-CHECKPOINT-V2\0" + canonical
    ).hexdigest()
    value["entry_sha256"] = previous
    records.append(json.dumps(value, separators=(",", ":")))
output.write_text("\n".join(records) + "\n")
PY
chmod 0640 "$change/acquisition-checkpoints.jsonl"

python3 - "$ris" "$change/session.json" "$change/acquisition.jsonl" \
  "$change/acquisition-checkpoints.jsonl" "$change/capture-bindings.jsonl" \
  "$change/acquisition-summary.json" <<'PY'
import hashlib
import json
import pathlib
import struct
import sys

ris, session_path, acquisition_path, checkpoints_path, bindings_path, summary_path = (
    map(pathlib.Path, sys.argv[1:])
)
acquisition = [json.loads(line) for line in acquisition_path.read_text().splitlines()]
previous = "0" * 64
bindings = []
sequences = []
position = 0
for round_id in ("01", "02", "03"):
    for family in ("ipv4", "ipv6"):
        position += 1
        paths = [
            ris / round_id / f"{family}.request.json",
            ris / round_id / f"{family}.headers",
            ris / round_id / f"{family}.json",
            ris / round_id / f"{family}.meta.json",
        ]
        raw = [path.read_bytes() for path in paths]
        frame = hashlib.sha256(b"RIS-CAPTURE-FRAME-V1\0")
        for value in raw:
            frame.update(struct.pack(">Q", len(value)))
            frame.update(value)
        request = json.loads(raw[0])
        entry = {
            "sequence": position,
            "request_sha256": request["request_sha256"],
            "headers_sha256": hashlib.sha256(raw[1]).hexdigest(),
            "body_sha256": hashlib.sha256(raw[2]).hexdigest(),
            "metadata_sha256": hashlib.sha256(raw[3]).hexdigest(),
            "frame_sha256": frame.hexdigest(),
            "previous_sha256": previous,
        }
        canonical = json.dumps(entry, separators=(",", ":")).encode()
        previous = hashlib.sha256(
            b"RIS-CAPTURE-CHAIN-V1\0" + canonical
        ).hexdigest()
        entry["entry_sha256"] = previous
        bindings.append(entry)
        sequences.append({
            "sequence": position,
            "round": round_id,
            "family": family,
            "request_sha256": request["request_sha256"],
            "acquisition_entry_sha256": acquisition[position - 1]["entry_sha256"],
            "capture_entry_sha256": previous,
        })
bindings_path.write_text(
    "".join(json.dumps(item, separators=(",", ":")) + "\n" for item in bindings)
)
checkpoint_lines = checkpoints_path.read_text().splitlines()
summary = {
    "acquisition_id": json.loads(session_path.read_bytes())["acquisition_id"],
    "session_sha256": hashlib.sha256(session_path.read_bytes()).hexdigest(),
    "sequences": sequences,
    "request_tail_sha256": sequences[-1]["request_sha256"],
    "acquisition_tail_sha256": acquisition[-1]["entry_sha256"],
    "capture_tail_sha256": bindings[-1]["entry_sha256"],
    "checkpoint_tail_sha256": json.loads(checkpoint_lines[-1])["entry_sha256"],
}
summary["summary_sha256"] = hashlib.sha256(
    b"RIS-ACQUISITION-SUMMARY-V1\0"
    + json.dumps(summary, separators=(",", ":")).encode()
).hexdigest()
summary_path.write_text(json.dumps(summary, indent=2) + "\n")
PY
chmod 0640 "$change/capture-bindings.jsonl" "$change/acquisition-summary.json"

gate_audit_tmp=$(mktemp "$change/.gate-audit.XXXXXX")
trap 'rm -f "$gate_audit_tmp"' EXIT
: >"$gate_audit_tmp"
previous_gate=$(printf '0%.0s' {1..64})
sequence=0
for round in 01 02 03; do
  ((sequence+=1))
  gate_stdout=$(mktemp "$change/.gate-stdout.XXXXXX")
  gate_stderr=$(mktemp "$change/.gate-stderr.XXXXXX")
  set +e
  /app/bin/ris-evidence-gate /app/policy/visibility.conf \
    "$ris/$round/ipv4.json" "$ris/$round/ipv6.json" "$decisions/$round.json" \
    >"$gate_stdout" 2>"$gate_stderr"
  gate_rc=$?
  set -e
  if (( gate_rc != 0 )) || [[ -s $gate_stdout || -s $gate_stderr ]]; then
    cat "$gate_stderr" >&2
    rm -f "$gate_stdout" "$gate_stderr"
    exit 1
  fi
  chmod 0640 "$decisions/$round.json"
  python3 - "$gate_audit_tmp" "$sequence" "$round" "$decisions/$round.json" \
    "$gate_stdout" "$gate_stderr" "$previous_gate" \
    "$change/acquisition-checkpoints.jsonl" <<'PY'
import hashlib
import json
import pathlib
import sys

ledger, sequence, round_id, decision, stdout, stderr, previous, checkpoints = sys.argv[1:]
command = [
    "/app/bin/ris-evidence-gate",
    "/app/policy/visibility.conf",
    f"/app/change/ris/{round_id}/ipv4.json",
    f"/app/change/ris/{round_id}/ipv6.json",
    f"/app/change/decisions/{round_id}.json",
]
sha = lambda name: hashlib.sha256(pathlib.Path(name).read_bytes()).hexdigest()
entry = {
    "sequence": int(sequence),
    "round": round_id,
    "command": command,
    "exit_code": 0,
    "stdout_sha256": sha(stdout),
    "stderr_sha256": sha(stderr),
    "decision_sha256": sha(decision),
    "policy_sha256": sha("/app/policy/visibility.conf"),
    "checkpoint_sha256": hashlib.sha256(
        (pathlib.Path(checkpoints).read_text().splitlines()[int(sequence) - 1] + "\n").encode()
    ).hexdigest(),
    "previous_sha256": previous,
}
canonical = json.dumps(entry, separators=(",", ":"), ensure_ascii=False).encode()
entry["entry_sha256"] = hashlib.sha256(
    b"RIS-GATE-AUDIT-V2\0" + canonical
).hexdigest()
with pathlib.Path(ledger).open("a", encoding="utf-8") as stream:
    stream.write(json.dumps(entry, separators=(",", ":"), ensure_ascii=False) + "\n")
PY
  previous_gate=$(tail -n 1 "$gate_audit_tmp" | jq -r .entry_sha256)
  rm -f "$gate_stdout" "$gate_stderr"
done
mv -fT "$gate_audit_tmp" "$change/gate-executions.jsonl"
chmod 0640 "$change/gate-executions.jsonl"
trap - EXIT

python3 - "$decisions" "$change/decision.json" "$change_id" \
  "$approved_profile" "$change/acquisition.jsonl" "$change/gate-executions.jsonl" <<'PY'
import hashlib
import json
import pathlib
import sys

root, output, change_id, profile, acquisition, gate_audit = sys.argv[1:]
root = pathlib.Path(root)
rounds = {}
values = []
for round_id in ("01", "02", "03"):
    path = root / f"{round_id}.json"
    raw = path.read_bytes()
    value = json.loads(raw)
    if value.get("change_id") != change_id:
        raise SystemExit("gate change ID mismatch")
    decision = value.get("decision")
    selected = value.get("selected_profile")
    if decision == "APPLY_STANDBY":
        if selected != profile:
            raise SystemExit("gate profile mismatch")
    elif decision == "HOLD":
        if selected is not None:
            raise SystemExit("hold gate selected a profile")
    else:
        raise SystemExit("unknown gate decision")
    values.append(decision)
    rounds[round_id] = {
        "decision": decision,
        "sha256": hashlib.sha256(raw).hexdigest(),
    }
apply = all(value == "APPLY_STANDBY" for value in values)
consensus = {
    "change_id": change_id,
    "decision": "APPLY_STANDBY" if apply else "HOLD",
    "selected_profile": profile if apply else None,
    "reason": "unanimous_apply" if apply else "round_hold",
    "rounds": rounds,
    "evidence_chain_sha256": hashlib.sha256(
        pathlib.Path(acquisition).read_bytes()
    ).hexdigest(),
    "gate_chain_sha256": hashlib.sha256(
        pathlib.Path(gate_audit).read_bytes()
    ).hexdigest(),
}
pathlib.Path(output).write_text(
    json.dumps(consensus, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
)
PY
chmod 0640 "$change/decision.json"

python3 - "$decisions" "$change/decision.json" \
  "$change/gate-executions.jsonl" "$change/quorum.json" <<'PY'
import hashlib
import json
import pathlib
import sys

decisions, decision_path, gate_path, output = map(pathlib.Path, sys.argv[1:])
consensus = json.loads(decision_path.read_bytes())
votes = {
    round_id: json.loads((decisions / f"{round_id}.json").read_bytes())["decision"]
    for round_id in ("01", "02", "03")
}
value = {
    "change_id": consensus["change_id"],
    "votes": votes,
    "apply_count": sum(vote == "APPLY_STANDBY" for vote in votes.values()),
    "hold_count": sum(vote == "HOLD" for vote in votes.values()),
    "outcome": consensus["decision"],
    "decision_sha256": hashlib.sha256(decision_path.read_bytes()).hexdigest(),
    "gate_chain_sha256": hashlib.sha256(gate_path.read_bytes()).hexdigest(),
}
canonical = json.dumps(value, separators=(",", ":")).encode()
value["quorum_sha256"] = hashlib.sha256(
    b"RIS-QUORUM-V1\0" + canonical
).hexdigest()
output.write_text(json.dumps(value, indent=2) + "\n")
PY
chmod 0640 "$change/quorum.json"

python3 - "$change" <<'PY'
import hashlib
import json
import pathlib

root = pathlib.Path("/app/change")
sha = lambda name: hashlib.sha256((root / name).read_bytes()).hexdigest()
decision = json.loads((root / "decision.json").read_bytes())
value = {
    "change_id": decision["change_id"],
    "outcome": decision["decision"],
    "decision_sha256": sha("decision.json"),
    "quorum_sha256": sha("quorum.json"),
    "acquisition_summary_sha256": sha("acquisition-summary.json"),
    "checkpoint_chain_sha256": sha("acquisition-checkpoints.jsonl"),
    "gate_chain_sha256": sha("gate-executions.jsonl"),
}
value["certificate_sha256"] = hashlib.sha256(
    b"RIS-CONSENSUS-CERT-V1\0"
    + json.dumps(value, separators=(",", ":")).encode()
).hexdigest()
(root / "consensus-certificate.json").write_text(
    json.dumps(value, indent=2) + "\n"
)
PY
chmod 0640 "$change/consensus-certificate.json"

if find /app/bin /app/docs /app/etc/frr /app/policy /app/inventory /app/runbooks \
  -type l -print -quit | grep -q .; then
  echo "symlinked source input" >&2
  exit 1
fi
find /app/bin /app/docs /app/etc/frr /app/policy /app/inventory /app/runbooks \
  -type f -print0 | sort -z | xargs -0 sha256sum >"$change/source-inputs.sha256"
chmod 0640 "$change/source-inputs.sha256"

decision=$(jq -r '.decision' "$change/decision.json")
profile=$(jq -r '.selected_profile // ""' "$change/decision.json")
if [[ $decision == APPLY_STANDBY && $profile == "$approved_profile" ]]; then
  render_one=$(mktemp "$change/.render-one.XXXXXX")
  render_two=$(mktemp "$change/.render-two.XXXXXX")
  trap 'rm -f "$render_one" "$render_two"' EXIT
  /app/bin/frr-policy-render /app/policy /app/etc/frr/running.conf "$render_one"
  /app/bin/frr-policy-render /app/policy /app/etc/frr/running.conf "$render_two"
  cmp -s "$render_one" "$render_two" || {
    echo "renderer output is not reproducible" >&2
    exit 1
  }
  mv -fT "$render_one" "$change/frr.conf"
  rm -f "$render_two"
  trap - EXIT
elif [[ $decision == HOLD && -z $profile ]]; then
  install -m 0640 /app/etc/frr/running.conf "$change/frr.conf"
  cmp -s /app/etc/frr/running.conf "$change/frr.conf"
else
  echo "unexpected consensus decision/profile" >&2
  exit 1
fi
chmod 0640 "$change/frr.conf"

python3 - "$change" <<'PY'
import hashlib
import json
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
value = {
    "renderer": "/app/bin/frr-policy-render",
    "renderer_sha256": sha(pathlib.Path("/app/bin/frr-policy-render")),
    "source_manifest_sha256": sha(root / "source-inputs.sha256"),
    "baseline_sha256": sha(pathlib.Path("/app/etc/frr/running.conf")),
    "candidate_sha256": sha(root / "frr.conf"),
    "reproducible": True,
}
(root / "render-provenance.json").write_text(
    json.dumps(value, indent=2) + "\n", encoding="utf-8"
)
PY
chmod 0640 "$change/render-provenance.json"

set +e
diff -u --label /app/etc/frr/running.conf --label /app/change/frr.conf \
  /app/etc/frr/running.conf "$change/frr.conf" >"$change/candidate.patch"
diff_rc=$?
set -e
if (( diff_rc > 1 )); then
  rm -f "$change/candidate.patch"
  echo "candidate diff failed" >&2
  exit 1
fi
python3 - "$change" <<'PY'
import hashlib
import json
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
sha = lambda name: hashlib.sha256((root / name).read_bytes()).hexdigest()
lines = (root / "candidate.patch").read_bytes().splitlines()
value = {
    "baseline_sha256": hashlib.sha256(
        pathlib.Path("/app/etc/frr/running.conf").read_bytes()
    ).hexdigest(),
    "candidate_sha256": sha("frr.conf"),
    "patch_sha256": sha("candidate.patch"),
    "added_lines": sum(line.startswith(b"+") and not line.startswith(b"+++") for line in lines),
    "removed_lines": sum(line.startswith(b"-") and not line.startswith(b"---") for line in lines),
}
value["delta_sha256"] = hashlib.sha256(
    b"RIS-CANDIDATE-DELTA-V1\0"
    + json.dumps(value, separators=(",", ":")).encode()
).hexdigest()
(root / "candidate-delta.json").write_text(json.dumps(value, indent=2) + "\n")
PY
chmod 0640 "$change/candidate.patch" "$change/candidate-delta.json"

validator_version=$(mktemp "$change/.validator-version.XXXXXX")
trap 'rm -f "$validator_version"' EXIT
dpkg-query -W '-f=${Version}\n' frr >"$validator_version"
validator_path=$(realpath "$(command -v vtysh)")
python3 - "$change" "$validator_path" "$validator_version" <<'PY'
import hashlib
import json
import pathlib
import sys

root, validator, version = map(pathlib.Path, sys.argv[1:])
value = {
    "command": "vtysh",
    "resolved_path": str(validator),
    "binary_sha256": hashlib.sha256(validator.read_bytes()).hexdigest(),
    "version_command": ["dpkg-query", "-W", "-f=${Version}\\n", "frr"],
    "version_output_sha256": hashlib.sha256(version.read_bytes()).hexdigest(),
}
value["attestation_sha256"] = hashlib.sha256(
    b"RIS-VALIDATOR-V1\0" + json.dumps(value, separators=(",", ":")).encode()
).hexdigest()
(root / "validator-attestation.json").write_text(json.dumps(value, indent=2) + "\n")
PY
rm -f "$validator_version"
trap - EXIT
chmod 0640 "$change/validator-attestation.json"

validation_codes=()
for validation_round in 01 02; do
  set +e
  vtysh -C -f "$change/frr.conf" \
    >"$change/frr-validate-$validation_round.log" 2>&1
  validation_codes+=("$?")
  set -e
  chmod 0640 "$change/frr-validate-$validation_round.log"
done
if (( validation_codes[0] != 0 || validation_codes[1] != 0 )) \
  || ! cmp -s "$change/frr-validate-01.log" "$change/frr-validate-02.log"; then
  rm -f "$change/frr.conf" "$change"/frr-validate-*.log
  echo "independent FRR validations failed or disagreed" >&2
  exit 1
fi

python3 - "$change" <<'PY'
import hashlib
import json
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
digest = lambda name: hashlib.sha256((root / name).read_bytes()).hexdigest()
value = {
    "commands": [
        ["vtysh", "-C", "-f", "/app/change/frr.conf"],
        ["vtysh", "-C", "-f", "/app/change/frr.conf"],
    ],
    "exit_codes": [0, 0],
    "candidate_sha256": digest("frr.conf"),
    "logs_sha256": [
        digest("frr-validate-01.log"),
        digest("frr-validate-02.log"),
    ],
    "logs_match": (
        (root / "frr-validate-01.log").read_bytes()
        == (root / "frr-validate-02.log").read_bytes()
    ),
    "decision_sha256": digest("decision.json"),
    "render_provenance_sha256": digest("render-provenance.json"),
    "source_manifest_sha256": digest("source-inputs.sha256"),
    "candidate_delta_sha256": digest("candidate-delta.json"),
    "validator_attestation_sha256": digest("validator-attestation.json"),
}
(root / "validation.json").write_text(
    json.dumps(value, indent=2) + "\n", encoding="utf-8"
)
PY
chmod 0640 "$change/validation.json"

rollback_codes=()
for rollback_round in 01 02; do
  set +e
  vtysh -C -f "$change/rollback.conf" \
    >"$change/rollback-validate-$rollback_round.log" 2>&1
  rollback_codes+=("$?")
  set -e
  chmod 0640 "$change/rollback-validate-$rollback_round.log"
done
if (( rollback_codes[0] != 0 || rollback_codes[1] != 0 )) \
  || ! cmp -s "$change/rollback-validate-01.log" \
    "$change/rollback-validate-02.log"; then
  rm -f "$change"/rollback-validate-*.log
  echo "independent rollback validations failed or disagreed" >&2
  exit 1
fi

python3 - "$change" "$change_id" "$router" "$approved_profile" <<'PY'
import email.parser
import hashlib
import json
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
change_id, router, profile = sys.argv[2:]
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
compact = lambda value: json.dumps(
    value, separators=(",", ":"), ensure_ascii=False
).encode()

def policy_values(path):
    values = {}
    for raw in pathlib.Path(path).read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values

visibility = policy_values("/app/policy/visibility.conf")
window = policy_values("/app/policy/maintenance/window.conf")
policy = {
    "change_id": change_id,
    "router": router,
    "ipv4_resource": visibility["ipv4_resource"],
    "ipv6_resource": visibility["ipv6_resource"],
    "expected_origin": int(visibility["expected_origin"]),
    "min_visibility_percent": int(visibility["min_visibility_percent"]),
    "standby_profile": profile,
    "approval": window["approval"],
    "visibility_policy_sha256": sha(pathlib.Path("/app/policy/visibility.conf")),
    "window_policy_sha256": sha(pathlib.Path("/app/policy/maintenance/window.conf")),
}
policy["attestation_sha256"] = hashlib.sha256(
    b"RIS-POLICY-ATTESTATION-V1\0" + compact(policy)
).hexdigest()
(root / "policy-attestation.json").write_text(
    json.dumps(policy, indent=2) + "\n"
)

transport_lines = []
previous = "0" * 64
sequence = 0
for round_id in ("01", "02", "03"):
    for family in ("ipv4", "ipv6"):
        sequence += 1
        base = root / "ris" / round_id / family
        header_path = base.with_suffix(".headers")
        request_path = base.with_suffix(".request.json")
        metadata_path = base.with_suffix(".meta.json")
        raw = header_path.read_bytes()
        status_line = raw.splitlines()[0].decode("ascii")
        headers = email.parser.BytesHeaderParser().parsebytes(
            b"".join(raw.splitlines(keepends=True)[1:])
        )
        metadata = json.loads(metadata_path.read_bytes())
        request = json.loads(request_path.read_bytes())
        entry = {
            "sequence": sequence,
            "round": round_id,
            "family": family,
            "status_line": status_line,
            "http_date": headers["Date"],
            "content_type": headers["Content-Type"],
            "remote_ip": metadata["remote_ip"],
            "tls_verified": metadata["tls_verified"],
            "request_sha256": request["request_sha256"],
            "headers_sha256": sha(header_path),
            "metadata_sha256": sha(metadata_path),
            "previous_sha256": previous,
        }
        entry["entry_sha256"] = hashlib.sha256(
            b"RIS-TRANSPORT-V1\0" + compact(entry)
        ).hexdigest()
        previous = entry["entry_sha256"]
        transport_lines.append(compact(entry).decode())
(root / "transport-ledger.jsonl").write_text(
    "\n".join(transport_lines) + "\n"
)

checkpoint_lines = [
    json.loads(line)
    for line in (root / "acquisition-checkpoints.jsonl").read_text().splitlines()
]
gate_lines = [
    json.loads(line)
    for line in (root / "gate-executions.jsonl").read_text().splitlines()
]
round_lines = []
previous = "0" * 64
for position, round_id in enumerate(("01", "02", "03")):
    artifacts = []
    for family in ("ipv4", "ipv6"):
        for suffix in ("request.json", "headers", "json", "meta.json"):
            path = root / "ris" / round_id / f"{family}.{suffix}"
            artifacts.append({
                "path": str(path),
                "sha256": sha(path),
                "bytes": path.stat().st_size,
            })
    decision_path = root / "decisions" / f"{round_id}.json"
    entry = {
        "round": round_id,
        "artifacts": artifacts,
        "decision_sha256": sha(decision_path),
        "checkpoint_entry_sha256": checkpoint_lines[position]["entry_sha256"],
        "gate_entry_sha256": gate_lines[position]["entry_sha256"],
        "previous_sha256": previous,
    }
    entry["entry_sha256"] = hashlib.sha256(
        b"RIS-ROUND-MANIFEST-V1\0" + compact(entry)
    ).hexdigest()
    previous = entry["entry_sha256"]
    round_lines.append(compact(entry).decode())
(root / "round-manifests.jsonl").write_text("\n".join(round_lines) + "\n")

rollback = {
    "commands": [
        ["vtysh", "-C", "-f", "/app/change/rollback.conf"],
        ["vtysh", "-C", "-f", "/app/change/rollback.conf"],
    ],
    "exit_codes": [0, 0],
    "rollback_sha256": sha(root / "rollback.conf"),
    "baseline_sha256": sha(pathlib.Path("/app/etc/frr/running.conf")),
    "logs_sha256": [
        sha(root / "rollback-validate-01.log"),
        sha(root / "rollback-validate-02.log"),
    ],
    "logs_match": (
        (root / "rollback-validate-01.log").read_bytes()
        == (root / "rollback-validate-02.log").read_bytes()
    ),
    "validator_attestation_sha256": sha(root / "validator-attestation.json"),
}
rollback["attestation_sha256"] = hashlib.sha256(
    b"RIS-ROLLBACK-VALIDATION-V1\0" + compact(rollback)
).hexdigest()
(root / "rollback-validation.json").write_text(
    json.dumps(rollback, indent=2) + "\n"
)

node_names = [
    "acquisition-summary.json",
    "consensus-certificate.json",
    "policy-attestation.json",
    "round-manifests.jsonl",
    "render-provenance.json",
    "rollback-validation.json",
    "validation.json",
]
nodes = [
    {"name": name, "sha256": sha(root / name)}
    for name in node_names
]
edges = [
    {"from": "acquisition-summary.json", "to": "round-manifests.jsonl"},
    {"from": "round-manifests.jsonl", "to": "consensus-certificate.json"},
    {"from": "policy-attestation.json", "to": "render-provenance.json"},
    {"from": "consensus-certificate.json", "to": "validation.json"},
    {"from": "render-provenance.json", "to": "validation.json"},
    {"from": "rollback-validation.json", "to": "validation.json"},
]
graph = {"nodes": nodes, "edges": edges}
graph["graph_sha256"] = hashlib.sha256(
    b"RIS-ARTIFACT-GRAPH-V1\0" + compact(graph)
).hexdigest()
(root / "artifact-graph.json").write_text(json.dumps(graph, indent=2) + "\n")

custody_sources = [
    ("acquired", "acquisition-summary.json"),
    ("transport_authenticated", "transport-ledger.jsonl"),
    ("rounds_closed", "round-manifests.jsonl"),
    ("decided", "consensus-certificate.json"),
    ("staged", "render-provenance.json"),
    ("candidate_validated", "validation.json"),
    ("rollback_validated", "rollback-validation.json"),
    ("graph_closed", "artifact-graph.json"),
]
custody_lines = []
previous = "0" * 64
for sequence, (stage, name) in enumerate(custody_sources, start=1):
    entry = {
        "sequence": sequence,
        "stage": stage,
        "artifact": f"/app/change/{name}",
        "artifact_sha256": sha(root / name),
        "previous_sha256": previous,
    }
    entry["entry_sha256"] = hashlib.sha256(
        b"RIS-CUSTODY-V1\0" + compact(entry)
    ).hexdigest()
    previous = entry["entry_sha256"]
    custody_lines.append(compact(entry).decode())
(root / "custody.jsonl").write_text("\n".join(custody_lines) + "\n")

decision = json.loads((root / "decision.json").read_bytes())
authorization = {
    "change_id": change_id,
    "router": router,
    "decision": decision["decision"],
    "selected_profile": decision["selected_profile"],
    "policy_attestation_sha256": sha(root / "policy-attestation.json"),
    "transport_ledger_sha256": sha(root / "transport-ledger.jsonl"),
    "round_manifest_tail_sha256": json.loads(round_lines[-1])["entry_sha256"],
    "rollback_validation_sha256": sha(root / "rollback-validation.json"),
    "artifact_graph_sha256": sha(root / "artifact-graph.json"),
    "custody_tail_sha256": previous,
    "consensus_certificate_sha256": sha(root / "consensus-certificate.json"),
    "validation_sha256": sha(root / "validation.json"),
}
authorization["authorization_sha256"] = hashlib.sha256(
    b"RIS-RELEASE-AUTHORIZATION-V1\0" + compact(authorization)
).hexdigest()
(root / "release-authorization.json").write_text(
    json.dumps(authorization, indent=2) + "\n"
)
PY
chmod 0640 "$change/policy-attestation.json" \
  "$change/transport-ledger.jsonl" "$change/round-manifests.jsonl" \
  "$change/rollback-validation.json" "$change/artifact-graph.json" \
  "$change/custody.jsonl" "$change/release-authorization.json"

python3 - "$change" <<'PY'
import hashlib
import json
import pathlib
import struct
import sys

root = pathlib.Path(sys.argv[1])
excluded = {
    "bundle-index.json", "bundle-merkle.json", "bundle-proofs.json",
    "signing-public.pem", "signing-key.json", "receipt.sha256",
    "receipt.sig", "commit.json",
}
paths = sorted(
    path for path in root.rglob("*")
    if path.is_file() and path.name not in excluded
)
index = []
leaves = []
for path in paths:
    raw = path.read_bytes()
    item = {
        "path": str(path),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "bytes": len(raw),
    }
    index.append(item)
    leaves.append(hashlib.sha256(
        b"\x00" + str(path).encode() + b"\x00" +
        bytes.fromhex(item["sha256"]) + struct.pack(">Q", item["bytes"])
    ).hexdigest())
(root / "bundle-index.json").write_text(
    json.dumps(index, indent=2) + "\n", encoding="utf-8"
)
levels = [leaves]
while len(levels[-1]) > 1:
    current = levels[-1]
    if len(current) % 2:
        current = [*current, current[-1]]
    levels.append([
        hashlib.sha256(
            b"\x01" + bytes.fromhex(current[pos]) +
            bytes.fromhex(current[pos + 1])
        ).hexdigest()
        for pos in range(0, len(current), 2)
    ])
merkle = {
    "algorithm": "sha256-domain-separated-v1",
    "leaf_count": len(leaves),
    "levels": levels,
    "root_sha256": levels[-1][0],
}
(root / "bundle-merkle.json").write_text(
    json.dumps(merkle, indent=2) + "\n", encoding="utf-8"
)
proofs = {}
for wanted in (
    "/app/change/decision.json",
    "/app/change/frr.conf",
    "/app/change/source-inputs.sha256",
    "/app/change/validation.json",
):
    index_number = next(
        number for number, item in enumerate(index) if item["path"] == wanted
    )
    position = index_number
    siblings = []
    for level in levels[:-1]:
        if position % 2:
            sibling_position = position - 1
            side = "left"
        else:
            sibling_position = position + 1 if position + 1 < len(level) else position
            side = "right"
        siblings.append({"side": side, "sha256": level[sibling_position]})
        position //= 2
    proofs[wanted] = {
        "index": index_number,
        "leaf_sha256": levels[0][index_number],
        "siblings": siblings,
    }
(root / "bundle-proofs.json").write_text(
    json.dumps(proofs, indent=2) + "\n", encoding="utf-8"
)
PY
chmod 0640 "$change/bundle-index.json" "$change/bundle-merkle.json" \
  "$change/bundle-proofs.json"

private_key=$(mktemp "$change/.signing-private.XXXXXX")
trap 'rm -f "$private_key"' EXIT
openssl genpkey -algorithm ED25519 -out "$private_key" >/dev/null 2>&1
openssl pkey -in "$private_key" -pubout -out "$change/signing-public.pem"
chmod 0640 "$change/signing-public.pem"

der_tmp=$(mktemp "$change/.signing-public.XXXXXX")
openssl pkey -pubin -in "$change/signing-public.pem" -outform DER \
  -out "$der_tmp"
python3 - "$change/signing-public.pem" "$der_tmp" \
  "$change/signing-key.json" <<'PY'
import hashlib
import json
import pathlib
import sys

pem, der, output = map(pathlib.Path, sys.argv[1:])
value = {
    "algorithm": "Ed25519",
    "public_key_sha256": hashlib.sha256(pem.read_bytes()).hexdigest(),
    "public_key_der_sha256": hashlib.sha256(der.read_bytes()).hexdigest(),
    "signature_target": "/app/change/receipt.sha256",
}
output.write_text(json.dumps(value, indent=2) + "\n")
PY
rm -f "$der_tmp"
chmod 0640 "$change/signing-key.json"

find "$change" -type f \
  ! -name receipt.sha256 ! -name receipt.sig ! -name commit.json \
  ! -name '.signing-private.*' -print0 \
  | sort -z | xargs -0 sha256sum >"$change/receipt.sha256"
chmod 0640 "$change/receipt.sha256"
openssl pkeyutl -sign -rawin -inkey "$private_key" \
  -in "$change/receipt.sha256" -out "$change/receipt.sig"
openssl pkeyutl -verify -rawin -pubin -inkey "$change/signing-public.pem" \
  -in "$change/receipt.sha256" -sigfile "$change/receipt.sig" >/dev/null
rm -f "$private_key"
trap - EXIT
chmod 0640 "$change/receipt.sig"

python3 - "$change" "$acquisition_id" <<'PY'
import hashlib
import json
import pathlib
import sys
from datetime import datetime, timezone

root = pathlib.Path(sys.argv[1])
sha = lambda name: hashlib.sha256((root / name).read_bytes()).hexdigest()
index = json.loads((root / "bundle-index.json").read_bytes())
merkle = json.loads((root / "bundle-merkle.json").read_bytes())
value = {
    "acquisition_id": sys.argv[2],
    "payload_count": len(index),
    "merkle_root_sha256": merkle["root_sha256"],
    "bundle_index_sha256": sha("bundle-index.json"),
    "bundle_proofs_sha256": sha("bundle-proofs.json"),
    "receipt_sha256": sha("receipt.sha256"),
    "signature_sha256": sha("receipt.sig"),
    "public_key_sha256": sha("signing-public.pem"),
    "signing_key_sha256": sha("signing-key.json"),
    "completed_at": datetime.now(timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%S.%fZ"
    ),
}
canonical = json.dumps(value, separators=(",", ":")).encode()
value["commit_sha256"] = hashlib.sha256(
    b"RIS-COMMIT-V1\0" + canonical
).hexdigest()
(root / "commit.json").write_text(
    json.dumps(value, indent=2) + "\n", encoding="utf-8"
)
PY
chmod 0640 "$change/commit.json"

find "$change" -type d -exec chmod 0750 {} +
find "$change" -type f -exec chmod 0640 {} +
if find "$change" -type l -o -type f -links +1 | grep -q .; then
  echo "unsafe retained artifact" >&2
  exit 1
fi
