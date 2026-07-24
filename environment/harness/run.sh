#!/bin/bash
if [ "$#" -ne 1 ]; then
  echo "usage: run.sh trace-file" >&2
  exit 2
fi
/app/bin/timers < "$1"
