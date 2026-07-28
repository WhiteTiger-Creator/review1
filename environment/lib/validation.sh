#!/usr/bin/env bash

# Lightweight schema probes used by the incomplete starter gate.
# Production validation must follow the authoritative ledger.

json_is_object() {
  jq -e 'type == "object"' "$1" >/dev/null 2>&1
}
