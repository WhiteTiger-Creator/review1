#!/usr/bin/env bash

# Starter formatter keeps payloads as compact JSON.
# Fortify formatting rules are owned by the ledger.

format_compact_json() {
  jq -c '.' <<<"$1"
}
