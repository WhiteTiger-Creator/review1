#!/bin/bash
set -euo pipefail

cp /solution/hall_transport.c /app/hall_transport.c
cc -O2 -std=c11 -Wall -Wextra -o /app/hall_transport /app/hall_transport.c -lm
/app/hall_transport /app/task_file/input_data /app/task_file/calibration
