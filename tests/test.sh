#!/bin/bash
set -uo pipefail

mkdir -p /logs/verifier
echo 0 > /logs/verifier/reward.txt

TEST_DIR="${TEST_DIR:-/tests}"
FIRST_DIR=/tmp/candidate_first
TRACE_FIRST=/tmp/candidate_trace_first.log
TRACE_SECOND=/tmp/candidate_trace_second.log
ARTIFACTS=(
    metrics.json
    candidate_results.csv
    fit_cv_results.csv
    fit_oof_predictions.csv
    fold_preprocessing_summary.csv
    predictions.csv
    validation_confusion_matrix.csv
    validation_class_report.csv
    validation_confidence_deciles.csv
    score_course_counterfactual.csv
    model_term_importance.csv
    preprocessing_summary.csv
    model_manifest.json
)

terminate_candidate_processes() {
    local candidate_uid
    local status_file
    local pid
    local uid

    candidate_uid="$(id -u candidate)"
    for status_file in /proc/[0-9]*/status; do
        [ -r "$status_file" ] || continue
        pid="${status_file#/proc/}"
        pid="${pid%/status}"
        uid="$(awk '/^Uid:/{print $2}' "$status_file")"
        if [ "$uid" = "$candidate_uid" ]; then
            kill -KILL "$pid" 2>/dev/null || true
        fi
    done
}

fail_verifier() {
    echo "Error: $1"
    echo 0 > /logs/verifier/reward.txt
    exit 1
}

terminate_candidate_processes
chown -R root:root "$TEST_DIR"
find "$TEST_DIR" -type d -exec chmod 0700 {} +
find "$TEST_DIR" -type f -exec chmod 0400 {} +

[ -f /app/analysis.R ] || fail_verifier "candidate analysis is missing"
[ ! -L /app/analysis.R ] || fail_verifier "candidate analysis must be a regular file"
command -v strace >/dev/null 2>&1 || fail_verifier "strace is required"

rm -rf /app/outputs "$FIRST_DIR"
rm -f "$TRACE_FIRST" "$TRACE_SECOND" /logs/verifier/ctrf.json
install -d -m 0700 -o root -g root "$FIRST_DIR"
sha256sum /opt/original_data/train.csv /opt/original_data/score.csv \
    > /tmp/original_input.sha256

run_candidate_once() {
    local trace_path="$1"
    rm -rf /app/outputs
    install -d -m 0755 -o candidate -g candidate /app/outputs
    strace -f -qq -e trace=%file -s 4096 -o "$trace_path" \
        runuser -u candidate -- Rscript /app/analysis.R
    local status=$?
    terminate_candidate_processes
    return "$status"
}

check_trace() {
    local trace_path="$1"
    local protected='(^|[[:space:],])"(/tests|/solution|/tmp/candidate_first)(/|")'
    if grep -E "$protected" "$trace_path" >/dev/null 2>&1; then
        fail_verifier "candidate attempted to access verifier-owned files"
    fi
}

check_inputs() {
    cmp -s /app/data/train.csv /opt/original_data/train.csv \
        || fail_verifier "train.csv was modified"
    cmp -s /app/data/score.csv /opt/original_data/score.csv \
        || fail_verifier "score.csv was modified"
}

if ! run_candidate_once "$TRACE_FIRST"; then
    fail_verifier "candidate analysis failed on the first run"
fi
check_trace "$TRACE_FIRST"
check_inputs
for artifact in "${ARTIFACTS[@]}"; do
    [ -f "/app/outputs/$artifact" ] \
        || fail_verifier "missing artifact $artifact"
    [ ! -L "/app/outputs/$artifact" ] \
        || fail_verifier "artifact $artifact is a symlink"
    install -m 0400 -o root -g root \
        "/app/outputs/$artifact" "$FIRST_DIR/$artifact"
done

if ! run_candidate_once "$TRACE_SECOND"; then
    fail_verifier "candidate analysis failed on the second run"
fi
check_trace "$TRACE_SECOND"
check_inputs
for artifact in "${ARTIFACTS[@]}"; do
    [ -f "/app/outputs/$artifact" ] \
        || fail_verifier "missing artifact $artifact on repeat run"
    [ ! -L "/app/outputs/$artifact" ] \
        || fail_verifier "repeat artifact $artifact is a symlink"
    cmp -s "$FIRST_DIR/$artifact" "/app/outputs/$artifact" \
        || fail_verifier "artifact $artifact is not deterministic"
done

cd "$TEST_DIR"
PYTHONDONTWRITEBYTECODE=1 PYTHONSAFEPATH=1 \
    python3 -P -m pytest -p no:cacheprovider --confcutdir="$TEST_DIR" \
    --ctrf /logs/verifier/ctrf.json test_outputs.py -v -rA
pytest_status=$?
if [ "$pytest_status" -eq 0 ]; then
    echo 1 > /logs/verifier/reward.txt
else
    echo 0 > /logs/verifier/reward.txt
fi
