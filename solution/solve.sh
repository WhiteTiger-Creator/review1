#!/bin/bash
set -euo pipefail

ROOT="${RAID_ROOT:-/app/work/raid-root}"

mkdir -p \
  "$ROOT/etc/mdadm/mdadm.conf.d" \
  "$ROOT/etc/default" \
  "$ROOT/etc/systemd/system" \
  "$ROOT/etc/raid-scrub" \
  "$ROOT/usr/local/lib/raid-scrub" \
  "$ROOT/var/lib/raid-scrub/checkpoints" \
  "$ROOT/var/lib/raid-scrub/state/bootmirror" \
  "$ROOT/var/lib/raid-scrub/state/data5" \
  "$ROOT/var/lib/raid-scrub/state/fast10" \
  "$ROOT/var/lib/raid-scrub/members/spares/boot" \
  "$ROOT/var/lib/raid-scrub/members/spares/data" \
  "$ROOT/var/lib/raid-scrub/members/spares/fast" \
  "$ROOT/var/lib/raid-scrub/alerts" \
  "$ROOT/var/lib/raid-scrub/locks"

cat > "$ROOT/etc/mdadm/mdadm.conf" <<'EOF'
# UUID-based assembly only; staged member metadata, never host disk nodes
DEVICE containers
MAILADDR root
EOF

cat > "$ROOT/etc/mdadm/mdadm.conf.d/10-bootmirror.conf" <<'EOF'
ARRAY /dev/md/bootmirror UUID=11111111-2222-3333-4444-555555555555 spare-group=boot bitmap=internal AUTO=yes
EOF

cat > "$ROOT/etc/mdadm/mdadm.conf.d/20-data5.conf" <<'EOF'
ARRAY /dev/md/data5 UUID=aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee spare-group=data bitmap=none AUTO=-all
EOF

cat > "$ROOT/etc/mdadm/mdadm.conf.d/30-fast10.conf" <<'EOF'
ARRAY /dev/md/fast10 UUID=ffffffff-0000-1111-2222-333333333333 spare-group=fast bitmap=internal
EOF

cat > "$ROOT/etc/default/mdadm" <<'EOF'
BOOT_DEGRADED=yes
RAID5_DEGRADED=refuse
EOF

cat > "$ROOT/etc/mdadm/spare-groups.conf" <<'EOF'
boot=var/lib/raid-scrub/members/spares/boot/spare0.meta
data=var/lib/raid-scrub/members/spares/data/spare0.meta
fast=var/lib/raid-scrub/members/spares/fast/spare0.meta
EOF

write_timer() {
  local name="$1"
  local day="$2"
  cat > "$ROOT/etc/systemd/system/raid-scrub-${name}.timer" <<EOF
[Unit]
Description=Monthly scrub for ${name}
[Timer]
OnCalendar=*-*-${day} 03:00:00
Persistent=true
Unit=raid-scrub-${name}.service
[Install]
WantedBy=timers.target
EOF
  cat > "$ROOT/etc/systemd/system/raid-scrub-${name}.service" <<EOF
[Unit]
Description=Scrub ${name}
[Service]
Type=oneshot
Environment=ARRAY_NAME=${name}
ExecStart=/usr/local/lib/raid-scrub/scrub-${name}.sh
EOF
  cat > "$ROOT/usr/local/lib/raid-scrub/scrub-${name}.sh" <<EOF
#!/bin/bash
set -euo pipefail
ROOT="\${RAID_ROOT:-/app/work/raid-root}"
STATE="\$ROOT/var/lib/raid-scrub/state/${name}/sync_action"
if [[ -f "\$STATE" ]] && [[ "\$(cat "\$STATE")" == "rebuild" ]]; then
  echo "skip scrub while rebuild in progress"
  exit 0
fi
echo "scrub ${name}"
EOF
  chmod +x "$ROOT/usr/local/lib/raid-scrub/scrub-${name}.sh"
}

# Windows: bootmirror 1..7, data5 8..14, fast10 15..28, every pair at least 7 apart.
write_timer bootmirror 1
write_timer data5 8
write_timer fast10 15

cat > "$ROOT/etc/raid-scrub/speed-limits.conf" <<'EOF'
speed_limit_min=1000
speed_limit_max=200000
EOF

# Ceilings meet the published floors (20000/80000/60000) and consume the whole
# 200000 global maximum with nothing left unassigned.
cat > "$ROOT/etc/raid-scrub/io-budget.conf" <<'EOF'
bootmirror=20000
data5=100000
fast10=80000
EOF

cat > "$ROOT/etc/raid-scrub/urgency.conf" <<'EOF'
urgent=data5
EOF

cat > "$ROOT/etc/raid-scrub/repair.authorize" <<'EOF'
aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee
EOF

cat > "$ROOT/etc/raid-scrub/repair.quorum" <<'EOF'
# repair epochs authorized by the storage change board
epoch=*
EOF

cat > "$ROOT/usr/local/lib/raid-scrub/notify.sh" <<'EOF'
#!/bin/bash
set -euo pipefail
ROOT="${RAID_ROOT:-/app/work/raid-root}"
ALERT_DIR="$ROOT/var/lib/raid-scrub/alerts"
mkdir -p "$ALERT_DIR"
STATE_FILE="$ALERT_DIR/last-state.json"
SEEN="$ALERT_DIR/seen_degraded"

event="${1:-}"
array="${2:-}"
uuid="${3:-}"

# Capture state before removal notices
printf '{"event":"%s","array":"%s","uuid":"%s"}\n' "$event" "$array" "$uuid" > "$STATE_FILE"

case "$event" in
  degraded)
    if [[ -f "$SEEN" ]] && grep -qx "$uuid" "$SEEN"; then
      # suppress duplicate degraded alerts
      exit 0
    fi
    echo "$uuid" >> "$SEEN"
    echo "alert degraded array=$array uuid=$uuid"
    ;;
  recovery|recovered)
    echo "alert recovered array=$array uuid=$uuid"
    ;;
  *)
    echo "alert event=$event array=$array"
    ;;
esac
EOF
chmod +x "$ROOT/usr/local/lib/raid-scrub/notify.sh"

# Retire any journal carrying the upper case damage marker, then stage a live
# offset so the parity array still resumes.
CPDIR="$ROOT/var/lib/raid-scrub/checkpoints"
shopt -s nullglob
for cp in "$CPDIR"/*.offset; do
  if grep -q 'CORRUPT' "$cp"; then
    mv -f "$cp" "${cp}.bad"
  fi
done
shopt -u nullglob
echo "1048576" > "$CPDIR/data5.offset"

echo "idle" > "$ROOT/var/lib/raid-scrub/state/bootmirror/sync_action"
echo "idle" > "$ROOT/var/lib/raid-scrub/state/data5/sync_action"
echo "idle" > "$ROOT/var/lib/raid-scrub/state/fast10/sync_action"

for g in boot data fast; do
  meta="$ROOT/var/lib/raid-scrub/members/spares/$g/spare0.meta"
  if [[ ! -f "$meta" ]]; then
    echo "spare=$g" > "$meta"
  fi
done

mkdir -p "$ROOT/var/lib/raid-scrub/members/foreign"
echo "foreign" > "$ROOT/var/lib/raid-scrub/members/foreign/foreign.flag"

bash -n "$ROOT/usr/local/lib/raid-scrub/notify.sh"
for s in bootmirror data5 fast10; do
  bash -n "$ROOT/usr/local/lib/raid-scrub/scrub-${s}.sh"
done

if command -v mdadm >/dev/null 2>&1; then
  mdadm --help >/dev/null
fi

/opt/raid-scrub/bin/raidscrubctl apply
