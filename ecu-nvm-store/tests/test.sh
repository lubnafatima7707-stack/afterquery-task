#!/bin/bash
set -uo pipefail

mkdir -p /logs/verifier
# The reward channel has to be out of reach of the unprivileged user the store
# runs as, and of anything it leaves behind: only root, which runs this script
# and pytest, may enter or write here.
chown root:root /logs/verifier
chmod 700 /logs/verifier

cd /tests
python -m pytest -q -p no:cacheprovider --ctrf /logs/verifier/ctrf.json test_verify.py > /logs/verifier/pytest.log 2>&1
code=$?

if [ "$code" -eq 0 ]; then
  printf "1" > /logs/verifier/reward.txt
else
  printf "0" > /logs/verifier/reward.txt
fi

cat /logs/verifier/pytest.log
exit 0
