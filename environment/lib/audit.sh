#!/usr/bin/env bash

audit_profile() {
  local profile="$1"
  local trace="$2"
  local report="$3"

  require_input "$profile"
  require_input "$trace"
  require_absolute "$report"

  jq -e . "$profile" >/dev/null 2>&1 || fail 65 "invalid profile"
  jq -s -e . "$trace" >/dev/null 2>&1 || fail 65 "invalid trace"

  local result
  result=$(
    jq -n \
      --slurpfile profile "$profile" \
      --slurpfile events "$trace" '
        [$profile[0].sysctls[].names[]] as $allowed |
        [$events[] | select(.sysctl as $call | $allowed | index($call) | not)
          | {seq, sysctl, reason: "not_fortified"}] as $violations |
        {
          status: (if ($violations | length) == 0 then "pass" else "violation" end),
          events_total: ($events | length),
          allowed_events: (($events | length) - ($violations | length)),
          violation_events: ($violations | length),
          violations: $violations
        }
      '
  ) || fail 65 "cannot audit trace"

  atomic_write_bytes "$report" "$(format_compact_json "$result")"
}
