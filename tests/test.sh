#!/bin/bash
# Default to failure so the verifier never exits without a reward file.
mkdir -p /logs/verifier
echo 0 > /logs/verifier/reward.txt

# Deny the candidate binary (which the suite runs unprivileged) any path into the
# verifier-only trees: the expected outputs under /tests, the oracle under
# /solution, and the reward file under /logs/verifier. The root verifier is
# unaffected; an unprivileged process cannot traverse a 0700 directory.
chmod 700 /logs/verifier /tests /solution 2>/dev/null

# Run pytest from an isolated, root-owned directory (/tests) with a clean import
# path so an agent-planted pytest.py or conftest.py under the writable
# /app/environment cannot shadow the real modules. PYTHONSAFEPATH keeps the cwd
# and any script directory off sys.path; confcutdir/rootdir stop conftest
# discovery from walking up into the agent's tree.
#
# The run counts only when the CTRF report it produced verifies as a genuine,
# complete pass (check_ctrf.py): pytest must exit 0 AND every collected test must
# be present and passed. Chaining the checker with && makes the combined exit
# status 0 only in that case, so a stub that merely fakes pytest's exit code
# earns nothing.
cd /tests || exit 1
CTRF=/logs/verifier/ctrf.json
PYTHONSAFEPATH=1 PYTHONDONTWRITEBYTECODE=1 PYTHONPATH= \
  /opt/verifier-venv/bin/python -m pytest \
  -p no:cacheprovider --import-mode=importlib \
  --rootdir=/tests --confcutdir=/tests \
  --ctrf "$CTRF" /tests/test_outputs.py -v -rA \
  && PYTHONSAFEPATH=1 PYTHONPATH= \
     /opt/verifier-venv/bin/python /tests/check_ctrf.py "$CTRF"
rc=$?
if [ "$rc" -eq 0 ]; then
    echo 1 > /logs/verifier/reward.txt
else
    echo 0 > /logs/verifier/reward.txt
fi
