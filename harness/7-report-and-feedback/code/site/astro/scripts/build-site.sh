#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")" && git rev-parse --show-toplevel)
PROJECT=$ROOT/harness/7-report-and-feedback/code/site/astro
OUTPUT=$ROOT/website/site
cd "$PROJECT"
[[ -d node_modules ]] || npm ci --ignore-scripts

# The build input is per-host instance data: every results/<host>/ that carries a
# site-config.json is auto-discovered and merged into one input -- a temp dir of
# <host> symlinks into results/ plus a merged site-config.json whose benchmark and
# image paths are prefixed with <host>/. STUDY=<host> builds a single host instead.
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
MERGED=$(python3 - "$ROOT" "$TMP" <<'MERGE'
import json, os, pathlib, sys
root, tmp = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
study = os.environ.get("STUDY", "").strip()
hosts = sorted(p.parent.name for p in (root / "results").glob("*/site-config.json"))
if study:
    hosts = [h for h in hosts if h == study] or sys.exit(
        f"STUDY={study}: no site-config.json under results/{study}/")
if not hosts:
    sys.exit("no results/<host>/site-config.json found: nothing to build")
merged = {"schema_version": 1, "site": None, "devices": []}
labels = set()
for h in hosts:
    cfg = json.loads((root / "results" / h / "site-config.json").read_text())
    if merged["site"] is None:
        merged["site"] = cfg["site"]  # site identity is repo-wide; first host supplies it
    for dev in cfg["devices"]:
        if dev["label"] in labels:
            sys.exit(f"duplicate device label {dev['label']!r} across hosts")
        labels.add(dev["label"])
        dev = dict(dev)
        dev["benchmarks"] = [f"{h}/{b}" for b in dev["benchmarks"]]
        dev["image"] = f"{h}/{dev['image']}"
        merged["devices"].append(dev)
    (tmp / h).symlink_to(root / "results" / h, target_is_directory=True)
# Optional per-device "order" (lower first); unordered devices keep host-name order after them.
# sorted() is stable, so equal keys preserve the host-name order established above.
merged["devices"].sort(key=lambda d: (d.get("order") is None, d.get("order") or 0))
(tmp / "site-config.json").write_text(json.dumps(merged, indent=1) + "\n")
print(f"merged {len(hosts)} host(s) [{', '.join(hosts)}], {len(merged['devices'])} device(s)")
MERGE
)
echo "$MERGED"

REPORT_SITE_INPUT="$TMP" npm run build
rm -rf "$OUTPUT"
mkdir -p "$OUTPUT"
cp -a dist/. "$OUTPUT/"

# Leak gate (CLAUDE.md, NON-NEGOTIABLE): this output is published to GitHub Pages.
# Refuse it if it carries operator paths, non-loopback IPs, or access details.
LEAKS=$(grep -rnIoE '/home/[A-Za-z0-9_.-]+|/Users/[A-Za-z0-9_.-]+|passwordless|NOPASSWD|tailnet|tailscale|wireguard|BEGIN [A-Z ]*PRIVATE KEY|\b([0-9]{1,3}\.){3}[0-9]{1,3}\b' "$OUTPUT" \
  | grep -vE ':(127\.0\.0\.1|0\.0\.0\.0)$' || true)
if [[ -n $LEAKS ]]; then
  echo "FATAL: site output carries access/infrastructure details:" >&2
  echo "$LEAKS" | head -20 >&2
  exit 1
fi

# website/ is git-ignored scratch space, but it is where a human lands first. Emit
# its README from this script so the build/preview instructions here can never rot
# independently of the script they describe (the previous hand-written copy pointed at
# a build script path that stopped existing months ago).
cat > "$ROOT/website/README.md" <<'SITE_README'
# website/ - generated site output

Everything here is generated and git-ignored; do not edit it, and expect this file to
be rewritten on every build. Tracked inputs are each host's results/<host>/
directory (site config, device image, and the publication JSON files it lists) and
the generator in harness/7-report-and-feedback/code/site/. How the renderer works,
and the data contracts it consumes, are documented in
harness/7-report-and-feedback/code/site/README.md - that file is the authority.

## Build

```bash
make build-site                     # from the repository root (all hosts)
STUDY=<host-dir> make build-site    # one host only
# equivalent, called directly:
harness/7-report-and-feedback/code/site/astro/scripts/build-site.sh
```

Every results/<host>/ that carries a site-config.json is discovered and merged into
one build. Either way it validates the inputs, builds to the generator's dist/,
replaces website/site/ with that output, and prints the path of the benchmarks index.

## Preview

```bash
# Serve what this build published.
python3 -m http.server 4321 --directory website/site --bind 127.0.0.1
open http://127.0.0.1:4321/benchmarks/
```

```bash
# Or let Astro serve its own dist/ instead of website/site/.
cd harness/7-report-and-feedback/code/site/astro
npm run preview -- --port 4321
open http://localhost:4321/benchmarks/
```

`astro preview` binds IPv6 `::1` only unless you pass `--host`: the server prints
"ready", `http://localhost:4321` works, and `http://127.0.0.1:4321` returns an empty
reply. Add `--host` to reach the site from another machine.

Verify the page you expect is really being served, rather than inferring it from a
server that started without error:

```bash
curl -s http://127.0.0.1:4321/benchmarks/ | grep -o 'href="[^"]*"' | sort -u
```

If that curl returns nothing, or the page 500s, the port is probably held by an older
server: check with `lsof -nP -iTCP:4321 -sTCP:LISTEN`, or pick another port. A dev or
preview server stages its data when it starts, so it will not show a report published
after that moment - restart it after building. Two servers can also hold the same port
number on different families (`::1` and 127.0.0.1), in which case the same URL answers
differently depending on how `localhost` resolves; pass `--host 127.0.0.1` to pin it.

For live editing instead of serving a build, `npm run dev` needs an input directory
too -- point it at one host's data:

```bash
REPORT_SITE_INPUT=$PWD/results/<host-dir> \
  npm run dev -- --host 127.0.0.1 --port 4321
```

Without it `prepare.mjs` fails with `ENOENT ... example/site-config.json`, which looks
nothing like the missing variable it actually is.
SITE_README

# R-06-10's lesson applies to files we write too: assert by re-reading, not by exit code.
grep -q 'astro preview' "$ROOT/website/README.md" \
  || { echo "FATAL: generated website/README.md lost its preview instructions" >&2; exit 1; }

echo "$OUTPUT/benchmarks/index.html"
