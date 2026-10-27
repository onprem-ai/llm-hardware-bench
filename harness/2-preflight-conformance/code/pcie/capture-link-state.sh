#!/usr/bin/env bash
# Lightweight read-only start/end link snapshot suitable for a run directory.
set -euo pipefail
OUT=${1:?usage: capture-link-state.sh OUTPUT.json}
TMP="${OUT}.tmp"
mkdir -p "$(dirname "$OUT")"
python3 - "$TMP" <<'PY'
import datetime, json, pathlib, subprocess, sys

def run(*cmd):
    p=subprocess.run(cmd,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    return {"command":list(cmd),"returncode":p.returncode,"stdout":p.stdout,"stderr":p.stderr}

query=run("nvidia-smi","--query-gpu=index,uuid,pci.bus_id,pcie.link.gen.current,pcie.link.gen.max,pcie.link.width.current,pcie.link.width.max","--format=csv,noheader,nounits")
gpus=[]
if query["returncode"] == 0:
    for line in query["stdout"].splitlines():
        values=[x.strip() for x in line.split(",")]
        if len(values) != 7: continue
        index,uuid,bdf,gc,gm,wc,wm=values
        sysfs=pathlib.Path("/sys/bus/pci/devices")/bdf.lower()
        def read(name):
            try: return (sysfs/name).read_text().strip()
            except OSError: return None
        gpus.append({"index":int(index),"uuid":uuid,"pci_bus_id":bdf.lower(),
                     "nvidia_smi":{"generation_current":gc,"generation_max":gm,
                                   "width_current":wc,"width_max":wm},
                     "sysfs":{"current_link_speed":read("current_link_speed"),
                              "current_link_width":read("current_link_width"),
                              "max_link_speed":read("max_link_speed"),
                              "max_link_width":read("max_link_width"),
                              "numa_node":read("numa_node")}})
doc={"schema_version":1,"captured_at":datetime.datetime.now(datetime.timezone.utc).isoformat(),
     "gpus":gpus,"nvidia_smi_query":query}
pathlib.Path(sys.argv[1]).write_text(json.dumps(doc,indent=2)+"\n")
PY
mv "$TMP" "$OUT"
