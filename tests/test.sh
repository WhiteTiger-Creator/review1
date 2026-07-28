#!/bin/bash

mkdir -p /logs/verifier
cd /app || exit 1

/usr/bin/python3 -m pytest /tests/test_outputs.py -rA
exit_code=$?

if [ "$exit_code" -eq 0 ]; then
  echo 1 > /logs/verifier/reward.txt
else
  echo 0 > /logs/verifier/reward.txt
fi
