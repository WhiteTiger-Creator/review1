#!/usr/bin/env bash

# Argument helpers for the kernel fortify gate CLI.
# Exact option contracts are defined in the ground lockdown ledger.

count_options() {
  printf '%s\n' "$@" | awk 'NR % 2 == 1 { print }' | wc -l
}
