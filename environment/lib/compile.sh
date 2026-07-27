#!/usr/bin/env bash

compile_profile() {
  local policy="$1"
  local manifest="$2"
  local output="$3"

  require_input "$policy"
  require_input "$manifest"
  require_absolute "$output"
  require_input "$CATALOG_PATH"

  jq -e . "$policy" "$manifest" "$CATALOG_PATH" >/dev/null 2>&1 \
    || fail 65 "invalid JSON input"

  local profile
  profile=$(
    jq -n \
      --slurpfile catalog "$CATALOG_PATH" \
      --slurpfile policy "$policy" \
      --slurpfile manifest "$manifest" '
        ($catalog[0]) as $catalog |
        ($policy[0]) as $policy |
        ($manifest[0]) as $manifest |
        ([ $catalog.baseline[] ]
          + [ $manifest.features[] as $feature | $catalog.features[$feature][] ]
          + $manifest.additional_sysctls | unique) as $names |
        {
          defaultAction: $policy.default_action,
          lockdownModes: $policy.lockdown_modes,
          sysctls: [{names: $names, action: "LOCK_ACT_ALLOW"}]
        }
      '
  ) || fail 65 "cannot compile profile"

  atomic_write_bytes "$output" "$(format_compact_json "$profile")"
  printf '%s' "$(jq -r '.station_id' "$manifest")" > "${output}.station"
}
