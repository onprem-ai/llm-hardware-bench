#!/usr/bin/env bash
set -uo pipefail
R=/home/demouser/glm53-raster
run_gen(){ local g=$1; cd "$R/$g" || return 1
  nohup bash run.sh >> controller.log 2>&1 & echo $! > "$R/$g/controller.pid"; wait $!; }
run_gen gen14-confirm-and-turnover
pid14=$(cat "$R/gen14-confirm-and-turnover/controller.pid" 2>/dev/null || true)
if [[ -z "$pid14" ]]; then echo "$(date -u +%FT%TZ) refusing to chain: empty controller pid" >> "$R/queue.log"; exit 1; fi
echo "$(date -u +%FT%TZ) gen14 finished pid=$pid14" >> "$R/queue.log"
if pgrep -f "run.sh" >/dev/null 2>&1; then echo "$(date -u +%FT%TZ) refusing to start gen15: another controller alive" >> "$R/queue.log"; exit 1; fi
if [[ -n "$(docker ps -q --filter publish=8080)" ]]; then echo "$(date -u +%FT%TZ) refusing to start gen15: 8080 still bound" >> "$R/queue.log"; exit 1; fi
run_gen gen15-expert-on-new-base
echo "$(date -u +%FT%TZ) queue drained" >> "$R/queue.log"
