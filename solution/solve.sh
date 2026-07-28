#!/bin/bash
set -euo pipefail

mkdir -p /app/bin
cat > /app/bin/vaultrelay_attest.pl <<'PL'
#!/usr/bin/env perl
use strict;
use warnings;
use Digest::SHA qw(hmac_sha256 sha256 sha256_hex);
use Encode qw(encode);
use File::Basename qw(basename);
use File::Path qw(make_path);
use HTTP::Tiny;
use JSON::PP;
use MIME::Base64 qw(decode_base64 encode_base64);

my $base_url = $ENV{VAULTRELAY_BASE_URL} // "http://127.0.0.1:8089";
my $request_glob = $ENV{VAULTRELAY_REQUEST_GLOB} // "/app/requests/*.json";
my $profile_id = $ENV{VAULTRELAY_PROFILE_ID} // "merchant-loopback-day";
my $profile_port = int($ENV{VAULTRELAY_PROFILE_PORT} // 8088);
my $port_source = $ENV{VAULTRELAY_PORT_SOURCE} // "profile";
my $health_probe_url = $ENV{VAULTRELAY_HEALTH_URL} // "$base_url/healthz";
my $out = "/app/out/attestation.json";
my $keyring_path = $ENV{VAULTRELAY_KEYRING} // "/app/keyring/hmac_keys.json";
my @canonical_headers = qw((request-target) host x-vr-merchant x-vr-key-id x-vr-timestamp x-vr-nonce digest);
my $header_list = join(" ", @canonical_headers);

my $json = JSON::PP->new->canonical(1);
my $pretty = JSON::PP->new->canonical(1)->pretty(1);
my $keyring_raw = slurp($keyring_path);
my $keyring = $json->decode($keyring_raw);
my $host = $base_url;
$host =~ s{^https?://}{};

make_path("/app/out/evidence");
unlink $out if -e $out;

my @outcomes;
for my $file (sort glob($request_glob)) {
    my $spec = $json->decode(slurp($file));
    my $sample_id = $spec->{sample_id};
    my $attempts = $spec->{attempts} // 1;
    for my $attempt (1 .. $attempts) {
        my $body = canonical_body($spec->{body});
        my $body_sha_hex = sha256_hex($body);
        my $digest_header = "SHA-256=:" . encode_base64(sha256($body), "") . ":";
        my $key = select_key($keyring, $spec);
        my %headers = (
            "host" => $host,
            "x-vr-merchant" => $spec->{merchant_id},
            "x-vr-key-id" => $key->{key_id},
            "x-vr-timestamp" => $spec->{timestamp},
            "x-vr-nonce" => $spec->{nonce},
            "digest" => $digest_header,
        );
        my $canonical = join("\n",
            "(request-target): post $spec->{path}",
            "host: $headers{host}",
            "x-vr-merchant: $headers{'x-vr-merchant'}",
            "x-vr-key-id: $headers{'x-vr-key-id'}",
            "x-vr-timestamp: $headers{'x-vr-timestamp'}",
            "x-vr-nonce: $headers{'x-vr-nonce'}",
            "digest: $headers{digest}",
        );
        my $sig = encode_base64(hmac_sha256(encode("UTF-8", $canonical), decode_base64($key->{secret_b64})), "");
        my $signature_header = qq{keyId="$key->{key_id}",algorithm="hmac-sha256",headers="$header_list",signature="$sig"};
        my $res = HTTP::Tiny->new(timeout => 10)->post(
            "$base_url$spec->{path}",
            {
                headers => {
                    "Content-Type" => "application/json",
                    "X-VR-Merchant" => $spec->{merchant_id},
                    "X-VR-Key-Id" => $key->{key_id},
                    "X-VR-Timestamp" => $spec->{timestamp},
                    "X-VR-Nonce" => $spec->{nonce},
                    "Digest" => $digest_header,
                    "Signature" => $signature_header,
                },
                content => $body,
            },
        );
        my $payload = $json->decode($res->{content});
        my $reason = $payload->{reason};
        my $status = $reason eq "accepted" ? "accepted" : ($reason eq "replay_nonce" ? "replayed" : "rejected");
        push @outcomes, {
            sample_id => $sample_id,
            attempt => $attempt,
            merchant_id => $spec->{merchant_id},
            key_id => $key->{key_id},
            nonce => $spec->{nonce},
            timestamp => $spec->{timestamp},
            status => $status,
            http_status => int($res->{status}),
            reason => $reason,
            body_sha256_hex => $body_sha_hex,
            digest_header => $digest_header,
            signature_input_sha256 => sha256_hex($canonical),
            response_id => $payload->{response_id},
        };
    }
}

@outcomes = sort { $a->{sample_id} cmp $b->{sample_id} || $a->{attempt} <=> $b->{attempt} } @outcomes;
my $attestation = {
    schema_version => "vaultrelay-attestation/v1",
    generated_at => "2026-07-26T12:00:00Z",
    api_base_url => $base_url,
    replay_window_seconds => 300,
    canonical_headers => \@canonical_headers,
    supervision => {
        profile_id => $profile_id,
        profile_port => $profile_port,
        port_source => $port_source,
        health_probe_url => $health_probe_url,
        state_path => "/app/out/supervisor_state.json",
    },
    evidence => {
        strace_path => "/app/out/evidence/signing.strace",
        lsof_path => "/app/out/evidence/sockets.lsof",
        keyring_sha256 => sha256_hex($keyring_raw),
    },
    outcomes => \@outcomes,
};
write_file($out, $pretty->encode($attestation));

sub slurp {
    my ($path) = @_;
    open my $fh, "<:raw", $path or die "open $path: $!";
    local $/;
    return <$fh>;
}

sub write_file {
    my ($path, $content) = @_;
    open my $fh, ">:raw", $path or die "write $path: $!";
    print {$fh} $content;
    close $fh or die "close $path: $!";
}

sub canonical_body {
    my ($body) = @_;
    return JSON::PP->new->canonical(1)->utf8(1)->encode($body);
}

sub parse_time {
    my ($s) = @_;
    return $1 if $s =~ /^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z)$/;
    die "bad timestamp $s";
}

sub select_key {
    my ($ring, $spec) = @_;
    if ($spec->{force_key_id}) {
        for my $key (@{$ring->{keys}}) {
            return $key if $key->{key_id} eq $spec->{force_key_id};
        }
        die "forced key not found";
    }
    my @eligible = grep {
        $_->{merchant_id} eq $spec->{merchant_id}
        && $_->{purpose} eq "webhook-signing"
        && $_->{status} eq "active"
        && $_->{not_before} le $spec->{timestamp}
        && $spec->{timestamp} lt $_->{not_after}
    } @{$ring->{keys}};
    die "no active signing key for $spec->{sample_id}" unless @eligible;
    @eligible = sort { $b->{priority} <=> $a->{priority} || $a->{key_id} cmp $b->{key_id} } @eligible;
    return $eligible[0];
}
PL
chmod +x /app/bin/vaultrelay_attest.pl

cat > /app/run_vaultrelay_attestation.sh <<'SH'
#!/bin/bash
set -euo pipefail

PORT="${VAULTRELAY_PORT:-8089}"
PROFILE_ENV="$(mktemp)"
python3 - "$PROFILE_ENV" <<'PY'
import json
import os
import shlex
import sys
from pathlib import Path

profile_env = Path(sys.argv[1])
config_path = Path("/app/runtime/supervisor_profiles.json")
config = json.loads(config_path.read_text(encoding="utf-8"))
profile_id = os.environ.get("VAULTRELAY_PROFILE") or config["current_profile"]
profile = config["profiles"][profile_id]
profile_port = int(profile["port"])
if "VAULTRELAY_PORT" in os.environ and os.environ["VAULTRELAY_PORT"]:
    port = int(os.environ["VAULTRELAY_PORT"])
    port_source = "environment"
else:
    port = profile_port
    port_source = "profile"
base_url = f"http://127.0.0.1:{port}"
health_url = base_url + profile.get("health_path", "/healthz")
values = {
    "PORT": str(port),
    "BASE_URL": base_url,
    "PROFILE_ID": profile_id,
    "PROFILE_PORT": str(profile_port),
    "PORT_SOURCE": port_source,
    "HEALTH_URL": health_url,
    "KEYRING_PATH": profile["keyring_path"],
    "REQUEST_GLOB": profile["request_glob"],
}
profile_env.write_text("".join(f"{key}={shlex.quote(value)}\n" for key, value in values.items()), encoding="utf-8")
PY
# shellcheck disable=SC1090
source "$PROFILE_ENV"
rm -f "$PROFILE_ENV"
mkdir -p /app/out/evidence
rm -f /app/out/attestation.json /app/out/supervisor_state.json /app/out/evidence/signing.strace /app/out/evidence/sockets.lsof

VAULTRELAY_PORT="$PORT" VAULTRELAY_KEYRING="$KEYRING_PATH" python3 /app/api/vaultrelay_api.py >/tmp/vaultrelay-api.log 2>&1 &
api_pid=$!
trap 'kill "$api_pid" 2>/dev/null || true' EXIT

python3 - "$HEALTH_URL" <<'PY'
import sys
import time
import urllib.request

url = sys.argv[1]
for _ in range(60):
    try:
        with urllib.request.urlopen(url, timeout=0.2) as resp:
            if resp.status == 200:
                break
    except Exception:
        time.sleep(0.1)
else:
    raise SystemExit("VaultRelay API did not start")
PY

VAULTRELAY_BASE_URL="$BASE_URL" \
VAULTRELAY_KEYRING="$KEYRING_PATH" \
VAULTRELAY_REQUEST_GLOB="$REQUEST_GLOB" \
VAULTRELAY_PROFILE_ID="$PROFILE_ID" \
VAULTRELAY_PROFILE_PORT="$PROFILE_PORT" \
VAULTRELAY_PORT_SOURCE="$PORT_SOURCE" \
VAULTRELAY_HEALTH_URL="$HEALTH_URL" \
strace -f -o /app/out/evidence/signing.strace perl /app/bin/vaultrelay_attest.pl
lsof -nP -a -p "$api_pid" -iTCP > /app/out/evidence/sockets.lsof || true

python3 - "$api_pid" <<'PY'
import json
import sys
from collections import Counter
from pathlib import Path

attestation = json.loads(Path("/app/out/attestation.json").read_text(encoding="utf-8"))
counts = Counter(item["status"] for item in attestation["outcomes"])
state = {
    "selected_profile": attestation["supervision"]["profile_id"],
    "profile_port": attestation["supervision"]["profile_port"],
    "port_source": attestation["supervision"]["port_source"],
    "api_base_url": attestation["api_base_url"],
    "health_probe_url": attestation["supervision"]["health_probe_url"],
    "listener_pid": int(sys.argv[1]),
    "evidence": {
        "strace_path": attestation["evidence"]["strace_path"],
        "lsof_path": attestation["evidence"]["lsof_path"],
        "keyring_sha256": attestation["evidence"]["keyring_sha256"],
    },
    "counts": {
        "accepted": counts.get("accepted", 0),
        "rejected": counts.get("rejected", 0),
        "replayed": counts.get("replayed", 0),
        "total": len(attestation["outcomes"]),
    },
}
Path("/app/out/supervisor_state.json").write_text(json.dumps(state, sort_keys=True, indent=2) + "\n", encoding="utf-8")
PY
SH
chmod +x /app/run_vaultrelay_attestation.sh

/app/run_vaultrelay_attestation.sh
