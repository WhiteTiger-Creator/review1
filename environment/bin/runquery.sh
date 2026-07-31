#!/bin/bash
if [ -z "$1" ]; then
  echo "usage: ./runquery.sh 'MATCH ... RETURN ...'" 1>&2
  exit 2
fi
python3 /app/bin/run_query.py "$1"
