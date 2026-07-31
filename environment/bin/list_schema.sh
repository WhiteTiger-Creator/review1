#!/bin/bash
echo "Framework count:"
python3 /app/bin/run_query.py "MATCH (n:Framework) RETURN count(n) AS total" | tail -n +2
echo "Argument count:"
python3 /app/bin/run_query.py "MATCH (n:Argument) RETURN count(n) AS total" | tail -n +2
echo "Attack count:"
python3 /app/bin/run_query.py "MATCH (n:Attack) RETURN count(n) AS total" | tail -n +2
echo "CandidateSet count:"
python3 /app/bin/run_query.py "MATCH (n:CandidateSet) RETURN count(n) AS total" | tail -n +2
echo "RAISES count:"
python3 /app/bin/run_query.py "MATCH ()-[r:RAISES]->() RETURN count(r) AS total" | tail -n +2
echo "STRIKES count:"
python3 /app/bin/run_query.py "MATCH ()-[r:STRIKES]->() RETURN count(r) AS total" | tail -n +2
echo "UNDERCUTS count:"
python3 /app/bin/run_query.py "MATCH ()-[r:UNDERCUTS]->() RETURN count(r) AS total" | tail -n +2
echo "MEMBER count:"
python3 /app/bin/run_query.py "MATCH ()-[r:MEMBER]->() RETURN count(r) AS total" | tail -n +2
