#!/usr/bin/env bash
# Arm the prefill reproducibility rerun against a host that is currently unreachable.
#
# The node went offline at 10:00Z with no advance notice, which is the second time in
# three days. The lesson filed as R-05-13 was that evidence must leave the host as it is
# produced, and that a campaign should not depend on a human happening to be watching when
# the machine comes back. So this watcher does both: it waits for reachability, refuses to
# launch unless the node is actually idle, and rsyncs each finished run down while the next
# one is still executing.
#
# Touch /tmp/prefill-repro.ABORT to stop it. It never deletes anything on the node.
set -uo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")" && git rev-parse --show-toplevel)
NODE=${NODE:?set NODE=<user>@<host> for the benchmark node}
SSHO="-o ConnectTimeout=10 -o ServerAliveInterval=5 -o ServerAliveCountMax=3"
HARNESS=$ROOT/harness/3-deployment-raster/code/raster-harness
REMOTE_RASTER=/home/demouser/glm53-raster
REMOTE_STATE=$REMOTE_RASTER/prefill-repro-20260907
CONTAINER=radixark-glm53-repro
MIRROR=${MIRROR:-$ROOT/results/xe7740-8x-rtx6000/_local-evidence/xe7740-04/glm5.3/5-campaign/prefill-repro-20260907}
WATCH=${WATCH:-/tmp/prefill-repro-watch}
ABORT=/tmp/prefill-repro.ABORT
RELAUNCH_OK=/tmp/prefill-repro.RELAUNCH-ALLOWED
mkdir -p "$WATCH" "$MIRROR"
ATTEMPT_FILE=$WATCH/attempt
log() { echo "$(date -u +%FT%TZ) $*" | tee -a "$WATCH/watch.log"; }

[[ -f $ABORT ]] && { log "abort file present, not starting"; exit 0; }

# --- launch gate: refuse to touch a host that is doing anything else -------------------
gates() { # returns 0 only when the node is idle and complete
  ssh -o ConnectTimeout=12 -o ServerAliveInterval=5 "$NODE" '
    set -u
    fail() { echo "GATE_FAIL $*"; exit 1; }
    running=$(docker ps --format "{{.Names}}" 2>/dev/null | grep -E "radixark|vllm|sglang" | tr "\n" " ")
    [ -z "$running" ] || fail "container still running: $running"
    busy=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits | awk "\$1>1000{c++} END{print c+0}")
    [ "$busy" -eq 0 ] || fail "$busy of 8 GPUs reporting >1000 MiB used"
    avail=$(free -g | awk "NR==2{print \$7}")
    [ "$avail" -gt 700 ] || fail "host MemAvailable ${avail}GiB"
    [ -d /home/demouser/models/RadixArk--GLM-5.3-NVFP4--model ] || fail "model directory absent"
    [ -f /home/demouser/glm53-raster/telemetry.sh ] || fail "telemetry.sh absent"
    shm=$(ls /dev/shm 2>/dev/null | wc -l); [ "$shm" -lt 200 ] || fail "/dev/shm holds $shm objects"
    echo GATE_OK
  ' 2>/dev/null
}

# Liveness matters as much as existence: STARTED is a file, so a host that rebooted
# mid-run leaves a run that exists and never finishes. Report both signals and let the
# caller decide, rather than adopting a corpse for the remaining hours.
state_on_node() { ssh $SSHO -n "$NODE" "
    echo files=\$(ls $REMOTE_STATE/STARTED $REMOTE_STATE/COMPLETE $REMOTE_STATE/INVALID* $REMOTE_STATE/ABORTED 2>/dev/null | xargs -n1 basename 2>/dev/null | tr '\n' ',')
    echo container=\$(docker ps --format '{{.Names}}' 2>/dev/null | grep -c "^${CONTAINER}\$" || true)
    echo controller=\$(pgrep -fc 'prefill-repro-20260907.sh' 2>/dev/null || echo 0)
    # Recursive, and not under runs/: run_one puts any run whose seed_base is not the
    # default into the controls/ namespace, so a rerun that passes explicit seed bases
    # lands entirely in controls/. Counting runs/ here reported 0 exports while 10 were
    # on disk - which would have satisfied the "died before producing data" condition and
    # relaunched over finished measurements.
    echo exports=\$(find $REMOTE_STATE -name profile_export_aiperf.json -not -path '*/warmup/*' 2>/dev/null | wc -l)
  " 2>/dev/null; }

# A launch is only a launch once the node says so. The first version of this function
# returned after starting ssh, which hung for 17 minutes: the controller does
# `exec > >(tee -a controller.log)`, and that process substitution keeps the channel
# open for the life of the run, so ssh never saw EOF. Worse, the campaign HAD started
# (nohup.out said "started pid=...") while the watcher believed nothing had happened, so
# a naive restart of the watcher would have launched a second container - the exact
# two-launch deviation disclosed for the formal campaign. Hence: -f to stop the local
# wait, an intent marker written first, and adoption of an existing run instead of
# relaunching it.
launch() {
  local kind=${1:-first}
  log "launch_attempted kind=$kind (unverified until the node reports STARTED)"
  # The retry decision is reached only after the probe found a dead STARTED in the current
  # root, so a retry must never write there again - the numbering follows that fact rather
  # than a local counter that would still say attempt 1.
  if [[ "$kind" == "retry" ]]; then
    local n=$(( $(cat "$ATTEMPT_FILE" 2>/dev/null || echo 1) + 1 ))
    log "leaving $REMOTE_STATE exactly as the dead attempt left it; attempt $n gets a fresh root"
    REMOTE_STATE=$REMOTE_RASTER/"prefill-repro-20260907.attempt$n"
    echo $n > "$ATTEMPT_FILE"
  else
    echo 1 > "$ATTEMPT_FILE"
  fi
  # Each attempt gets its own evidence root, so no launch can share a directory with one
  # that died, and the dead root stays exactly as it is for inspection.

  ssh $SSHO -n "$NODE" "mkdir -p $REMOTE_STATE && rm -f $REMOTE_STATE/COMPLETE $REMOTE_STATE/INVALID* $REMOTE_STATE/ABORTED" || return 1
  scp -q "$HARNESS/prefill-repro-20260907.sh" "$NODE:$REMOTE_RASTER/prefill-repro-20260907.sh" || return 1
  local want got
  want=$(shasum -a 256 "$HARNESS/prefill-repro-20260907.sh" | cut -d' ' -f1)
  got=$(ssh $SSHO -n "$NODE" "sha256sum $REMOTE_RASTER/prefill-repro-20260907.sh" | cut -d' ' -f1)
  [[ "$want" == "$got" ]] || { log "launch refused: uploaded script hash mismatch"; return 1; }
  ssh $SSHO -f -n "$NODE" "cd $REMOTE_RASTER && setsid nohup bash prefill-repro-20260907.sh >$REMOTE_STATE/controller.log 2>&1 < /dev/null & exit 0"
  sleep 20
  state_on_node | grep -q STARTED
}

mirror() { # copy finished artifacts down, leaving the node's copy untouched
  rsync -aq --ignore-existing \
    -e "ssh $SSHO" \
    "$NODE:$REMOTE_STATE/" "$MIRROR/" 2>/dev/null
}

log "watcher start; waiting for $NODE"
while true; do
  if [[ -f $ABORT ]]; then log "ABORT seen; leaving node state as-is"; exit 0; fi

  if ! ssh -o ConnectTimeout=10 -o ServerAliveInterval=5 "$NODE" true 2>/dev/null; then
    sleep 60; continue
  fi

  if ! grep -q "launched" "$WATCH/watch.log" 2>/dev/null; then
    s=$(state_on_node)
    files=$(echo "$s" | sed -n 's/^files=//p')
    container=$(echo "$s" | sed -n 's/^container=//p')
    controller=$(echo "$s" | sed -n 's/^controller=//p')
    if echo "$files" | grep -qE "COMPLETE|INVALID|ABORTED"; then
      log "a previous run already ended here (files=$files); leaving it for inspection rather than relaunching"
      exit 5
    fi
    if echo "$files" | grep -q "STARTED"; then
      if [[ "${container:-0}" -gt 0 || "${controller:-0}" -gt 0 ]]; then
        log "adopting the in-flight run (container=$container controller=$controller files=$files); not relaunching - two launches would be a new deviation"
        log "launched (adopted)"
      else
        # Dying with no artifacts is a different event from dying at C64 having already
        # measured six points. The first is safe to retry inside the approved contract;
        # the second would mix two partial launches into one evidence root. So the retry
        # is bounded to exports=0, happens at most once, and is off unless a human put
        # the switch file in place first.
        dead_exports=$(echo "$s" | sed -n 's/^exports=//p' | tr -d ' ')
        if [[ -f $RELAUNCH_OK && "${dead_exports:-0}" -eq 0 ]] && ! grep -q "relaunched once" "$WATCH/watch.log"; then
          log "prior attempt died during startup with 0 exports; relaunching ONCE under the approved rerun contract"
          log "relaunched once"
          launch retry && log "launched" || log "relaunch attempt UNVERIFIED; will keep checking"
        else
          log "STARTED present but container=$container and controller=$controller: the run died (host reboot or reclaim)."
          log "not relaunching: switch=$([[ -f $RELAUNCH_OK ]] && echo present || echo absent) exports=${dead_exports:-unknown} - a partial campaign must not be resumed by a second launch"
          exit 4
        fi
      fi
    elif [[ "${container:-0}" -gt 0 ]]; then
      g=$(gates | tail -1)
      if [[ "$g" == "GATE_OK" ]]; then
        log "node reachable and idle; launching"
        if launch; then log "launched"; else log "launch attempted but UNVERIFIED; will keep checking"; fi
      else
        log "gate refused launch: $g"
        sleep 300; continue
      fi
    else
      log "container ${CONTAINER} is up with no STARTED marker; refusing to launch over it"
      exit 6
    fi
  else
    mirror
    n=$(find "$MIRROR" -name profile_export_aiperf.json -not -path '*/warmup/*' 2>/dev/null | wc -l | tr -d ' ')
    live=$(state_on_node)
    if echo "$live" | grep -qE "COMPLETE|INVALID|ABORTED"; then
      ssh "$NODE" "tail -5 $REMOTE_STATE/progress.log" >> "$WATCH/watch.log" 2>/dev/null
      mirror; mirror
      final=$(find "$MIRROR" -name profile_export_aiperf.json -not -path '*/warmup/*' 2>/dev/null | wc -l | tr -d ' ')
      log "rerun finished; $final/12 measured exports mirrored to $MIRROR"
      exit 0
    fi
    log "in progress: $n/12 exports mirrored; node says $(echo "$live" | tr '\n' ' ')"
  fi
  sleep 60
done
