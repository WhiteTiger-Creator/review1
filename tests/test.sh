#!/bin/bash

mkdir -p /logs/verifier
echo 0 > /logs/verifier/reward.txt

python3 -m pytest /tests/test_outputs.py -rA -q

if [ $? -eq 0 ]; then
  echo 1 > /logs/verifier/reward.txt
else
  echo 0 > /logs/verifier/reward.txt
fi
