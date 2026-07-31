#!/bin/bash
set -euo pipefail

mkdir -p /workspace/cmd/systemd-window-plan /workspace/bin /workspace/output
cp /solution/main.go /workspace/cmd/systemd-window-plan/main.go
cd /workspace/cmd/systemd-window-plan
GO111MODULE=off go build -o /workspace/bin/systemd-window-plan .
/workspace/bin/systemd-window-plan /workspace/task_file/window_request.json /workspace/output/window_plan.json
