#!/usr/bin/env bash
# Read-only probe for Intel IMC/UPI PMUs and access permissions.
set -uo pipefail
OUT=${1:-uncore-probe-$(date -u +%Y%m%dT%H%M%SZ)}
mkdir -p "$OUT"
exec > >(tee "$OUT/probe.log") 2>&1
printf 'captured_at=%s\n' "$(date -u --iso-8601=ns)"
printf 'perf_event_paranoid=%s\n' "$(cat /proc/sys/kernel/perf_event_paranoid 2>/dev/null || echo unavailable)"
find /sys/bus/event_source/devices -maxdepth 1 -type l -printf '%f\n' | grep -E '^uncore_(imc|upi)' | sort > "$OUT/pmus.txt" || true
for pmu in /sys/bus/event_source/devices/uncore_imc_* /sys/bus/event_source/devices/uncore_upi_*; do
 [[ -d $pmu ]] || continue
 name=$(basename "$pmu"); mkdir -p "$OUT/$name"
 cat "$pmu/type" > "$OUT/$name/type.txt" 2>/dev/null || true
 cp -a "$pmu/events" "$OUT/$name/" 2>/dev/null || true
 cp -a "$pmu/format" "$OUT/$name/" 2>/dev/null || true
done
status=unavailable
reason='no supported named IMC event or permission denied'
# Output redirections are deliberately performed by the caller into caller-owned OUT.
# shellcheck disable=SC2024
if command -v perf >/dev/null && grep -q '^uncore_imc_' "$OUT/pmus.txt"; then
 if perf stat -a -e 'uncore_imc/cas_count_read_sch0/' -- sleep 0.1 >"$OUT/perf-imc.stdout" 2>"$OUT/perf-imc.stderr"; then
  status=available_unprivileged; reason='perf named IMC event succeeded'
 # Redirections intentionally run as the unprivileged caller; OUT is caller-owned.
 elif sudo -n sh -c 'exec perf stat -a -e uncore_imc/cas_count_read_sch0/ -- sleep 0.1' >"$OUT/perf-imc-sudo.stdout" 2>"$OUT/perf-imc-sudo.stderr"; then
  status=available; reason='captured via perf'
 else
  status=permission_denied_or_unsupported; reason=$(tail -1 "$OUT/perf-imc.stderr")
 fi
fi
python3 - "$OUT/availability.json.tmp" "$status" "$reason" <<'PY'
import datetime,json,pathlib,sys
pathlib.Path(sys.argv[1]).write_text(json.dumps({'schema_version':1,'captured_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'imc_perf_status':sys.argv[2],'reason':sys.argv[3],'upi_named_events_present':any(pathlib.Path('/sys/bus/event_source/devices').glob('uncore_upi_*/events/*')),'semantics':'Unavailable counters are not zero.'},indent=2)+'\n')
PY
mv "$OUT/availability.json.tmp" "$OUT/availability.json"
cat "$OUT/availability.json"
