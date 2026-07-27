#!/usr/bin/env bash
# Mount table reader helper

mtab_x() {
  local remount_json="$1"
  python3 -c "import json,sys; d=json.load(open(sys.argv[1])); print(len(d.get('entries',[])))" "$remount_json"
}
