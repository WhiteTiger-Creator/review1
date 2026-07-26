#!/bin/bash
mkdir -p /logs/verifier
cd /tests
/opt/venv/bin/python -m pytest --ctrf /logs/verifier/ctrf.json -rA test_protocol.py
if [ $? -eq 0 ]; then
  echo 1 > /logs/verifier/reward.txt
else
  echo 0 > /logs/verifier/reward.txt
fi
