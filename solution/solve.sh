#!/bin/bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"

bash "$ROOT_DIR/apply_knot.sh"
bash "$ROOT_DIR/apply_quad.sh"
bash "$ROOT_DIR/apply_vial.sh"

cd /app
mvn -q -DskipTests package
mkdir -p /app/output
java -jar /app/drive/target/drive-1.0.0-shaded.jar
