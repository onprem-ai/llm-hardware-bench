#!/usr/bin/env python3
"""Cold prefill benchmark against any OpenAI-compatible endpoint, by URL and credential.

Mechanical by construction: one entry point, no hand-written campaign script, no judgement
left at the boundary. The prompt pool is built before measurement, the tool is probed with
the exact argument set before timing, and every run is judged cold or warm from the server's
own prefix-cache counters. A warm or unverified run is never reported as a number.

    export APIKEY=...
    ./cold-prefill-client.py --url https://host:port --model glm-5.3 \\
        --grid 1,8,32,64,96,128,160,192 --reps 3 --out ./cold-$(date +%Y%m%d)

Credentials are read from an environment variable, never from an argument: argv is visible in
`ps`, in shell history and in the child process a benchmark tool spawns. They are redacted in
every log line and file this tool writes.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import pathlib
import shlex
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import cold_gate  # noqa: E402  (same directory; one implementation of the verdict)

DEFAULT_GRID = "1,8,32,64,96,128,160,192"
# Flags this tool needs the installed build to support. Verified by --help probe, not assumed.
CORE_FLAGS = ("--concurrency", "--benchmark-duration", "--benchmark-grace-period",
              "--use-server-token-count", "--num-dataset-entries", "--extra-inputs",
              "--request-timeout-seconds", "--endpoint-type", "--streaming")
# Two vocabularies exist for the same controls. The 0.13 line renamed the synthetic length
# options and replaced --dataset-type with --custom-dataset-type; the build on the benchmark
# host predates that. Detecting which one is installed is the only way to avoid passing an
# option this build ignores -- and an ignored pool-size option is exactly the original defect.
VOCABULARIES = {
    "current": {"requires": ("--isl", "--osl", "--custom-dataset-type", "--server-metrics"),
                "isl": ("--isl", "--isl-stddev"), "osl": ("--osl", "--osl-stddev"),
                "corpus": ("--custom-dataset-type", "single_turn", "--input-file"),
                "synthetic": (), "sampling": "--dataset-sampling-strategy",
                "metrics": ("--server-metrics",)},
    "classic": {"requires": ("--dataset-type", "--synthetic-input-tokens-mean",
                             "--output-tokens-mean"),
                "isl": ("--synthetic-input-tokens-mean", "--synthetic-input-tokens-stddev"),
                "osl": ("--output-tokens-mean", "--output-tokens-stddev"),
                "corpus": ("--dataset-type", "custom", "--input-file"),
                "synthetic": ("--dataset-type", "synthetic"), "sampling": "",
                "metrics": ()},
}
# Credential flags differ by build; whichever exists is used, and if none does the tool
# refuses rather than sending an unauthenticated request or guessing a flag name.
AUTH_CANDIDATES = ("--api-key", "--bearer-token", "--api_key")


def env(name: str) -> str | None:
    value = os.environ.get(name, "").strip()
    return value or None


def probe(aiperf: str, needs_corpus: bool):
    """Return (ok, detail, vocabulary, auth_flag): what does this build actually accept?"""
    try:
        help_text = subprocess.run([aiperf, "profile", "--help"], capture_output=True,
                                   text=True, timeout=120).stdout
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, f"cannot run `{aiperf} profile --help`: {exc}", None, None
    vocab = next((name for name, spec in VOCABULARIES.items()
                  if all(f in help_text for f in spec["requires"])), None)
    if vocab is None:
        return False, ("neither known input-control vocabulary is fully present (expected "
                       "--isl/--osl/--custom-dataset-type or --dataset-type/"
                       "--synthetic-input-tokens-mean). Refusing to guess: an option this "
                       "build ignores restores the default 100-prompt pool."), None, None
    missing = [f for f in CORE_FLAGS if f not in help_text]
    if vocab == "current" and needs_corpus and "--input-file" not in help_text:
        # Absence is tested, not assumed. Appending unconditionally made a corpus impossible on
        # every `current` build, and the fallback it left open emits `--dataset-type synthetic`
        # -- synthetic prompts, the condition R-05-2 prohibits (R-PIPE-11: a gate never run
        # against the failure it guards is not a gate; this one was run and failed itself).
        missing = missing + ["--input-file"]
    if missing:
        return False, (f"build looks like `{vocab}` but lacks: " + ", ".join(missing)
                       + " -- refusing to measure with an option that would be ignored"), None, None
    auth = next((f for f in AUTH_CANDIDATES if f in help_text), None)
    if auth is None:
        return False, ("no recognised credential flag in this build (looked for "
                       + ", ".join(AUTH_CANDIDATES) + "); pass the real one via --auth-flag"), None, None
    return True, (f"vocabulary `{vocab}`; input controls verified in --help; credential "
                  f"flag {auth}"), vocab, auth


def build_inputs(args, out: pathlib.Path,
               tag: str | None = None) -> tuple[pathlib.Path, dict]:
    """Unique prompts, either from a book or from the synthetic generator."""
    stem = f"corpus-{tag}" if tag else "corpus"
    corpus = out / f"{stem}.jsonl"
    manifest = out / f"{stem}-manifest.json"
    if args.book:
        cmd = [sys.executable, str(HERE / "make_book_corpus.py"), "--source", args.book,
               "--out", str(corpus), "--manifest", str(manifest),
               "--prompts", str(args.prompts_needed), "--warmup-prompts", str(args.warmup_prompts),
               "--target-tokens", str(args.input_tokens)]
        if args.book_skip_head is not None:
            cmd += ["--skip-head", str(args.book_skip_head)]
        p = subprocess.run(cmd, capture_output=True, text=True)
        if p.returncode != 0:
            raise SystemExit(f"corpus build refused: {p.stderr.strip()}")
            # A claim about the pool is checked against the pool. The client once announced a
            # re-sized count it never built: the resize moved --num-dataset-entries while the
            # cutter reads --prompts-needed, so it measured on the old pool, wrapped, and served
            # 53.3% of prompt tokens from cache while reporting a much larger pool.
            have = sum(1 for line in corpus.read_text().split("\n") if line.strip())
            want = args.prompts_needed + args.warmup_prompts
            if have != want:
                raise SystemExit(f"corpus holds {have} records, expected {want} "
                    f"({args.prompts_needed} measured + {args.warmup_prompts} warm-up); "
                    "refusing to measure with an unsized pool")
        return corpus, json.loads(manifest.read_text())
    return corpus, {"mode": "synthetic", "num_dataset_entries": args.num_dataset_entries,
                    "note": "no --book given; pool sized above expected requests. The gate "
                            "still judges the outcome; a synthetic pool can collide."}


def _dataset_for_vocab(path: pathlib.Path, vocab: str) -> pathlib.Path:
    """Re-emit the prompt pool in the record shape this AIPerf vocabulary expects.

    0.13 validates each custom-dataset record and requires a modality field (`text`); the pool is
    authored as {"prompt": ...} because that is what the classic line accepted. Guessing the shape
    is not an option: a rejected record set produces no export at all, and the cold gate reports
    that as `unknown` -- correctly refusing to call it a measurement.
    """
    if vocab != "current":
        return path
    out = path.with_name(path.stem + "-text.jsonl")
    lines = []
    # Split on newline characters only, never str.splitlines(): that also breaks on U+2028,
    # U+2029 and U+0085, which json.dumps(ensure_ascii=False) leaves raw inside a record, so
    # one JSON object was cut in half and the client died with "Unterminated string".
    for line in path.read_text().split("\n"):
        if not line.strip():
            continue
        rec = json.loads(line)
        lines.append(json.dumps({"text": rec.get("prompt") or rec.get("text"),
                                 "passage_index": rec.get("passage_index")}))
    out.write_text("\n".join(lines) + "\n")
    return out


def command(args, out, concurrency, reps_seed, inputs: pathlib.Path | None,
            auth_flag: str | None, token: str | None) -> list[str]:
    spec = VOCABULARIES[getattr(args, "_vocab", "classic")]
    isl_mean, isl_std = spec["isl"]
    osl_mean, osl_std = spec["osl"]
    cmd = [args.aiperf, "profile", "--model", args.model, "--url", args.url,
           *(["--tokenizer", args.tokenizer] if args.tokenizer else []),
           "--endpoint-type", "chat", "--endpoint", args.endpoint, "--streaming",
           osl_mean, str(args.output_tokens), osl_std, "0",
           "--concurrency", str(concurrency),
           "--benchmark-duration", str(args.window_s), "--benchmark-grace-period", "inf",
           "--use-server-token-count", "--random-seed", str(reps_seed),
           "--extra-inputs", json.dumps({"temperature": 0, "ignore_eos": True}),
           "--request-timeout-seconds", str(args.request_timeout_s),
           "--output-artifact-dir", str(out)]
    if inputs is not None:
        # AIPerf 0.13 rejects prompt-length shaping with a custom dataset: "--isl /
        # --synthetic-input-tokens-mean is only supported with synthetic datasets; remove
        # --input-file". Prompt length therefore comes from the corpus itself -- passages are cut
        # to the target upstream -- and the realized ISL is whatever the server counts, not the
        # nominal --input-tokens. Emitting both flags produces an error and no export at all,
        # which the cold gate correctly reports as `unknown` rather than as a measurement.
        cmd += [isl_mean, str(args.input_tokens), isl_std, "0"] \
            if getattr(args, "_vocab", "classic") != "current" else []
        cmd += list(spec["corpus"]) + [str(_dataset_for_vocab(inputs, getattr(args, "_vocab", "classic")))]
    else:
        cmd += [isl_mean, str(args.input_tokens), isl_std, "0"]
        cmd += list(spec["synthetic"])
    cmd += ["--num-dataset-entries", str(args.num_dataset_entries)]
    if spec["sampling"]:
        # sequential walks the pool in order, so a pool larger than the window's demand is
        # never re-entered; random samples with replacement and may repeat early by design.
        cmd += [spec["sampling"], "sequential"]
    cmd += list(spec["metrics"])
    if auth_flag and token:                      # the token is a separate argv element so
        cmd += [auth_flag, token]                # redaction can match it exactly
    return cmd


def run(cmd: list[str], log: pathlib.Path, token: str | None) -> int:
    """Execute, redacting the credential from every trace we keep."""
    with log.open("w") as handle:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, env={**os.environ})
        assert proc.stdout is not None
        for line in proc.stdout:
            handle.write(line.replace(token, "[REDACTED]") if token else line)
        return proc.wait()


def throughput_from(run_dir: pathlib.Path, metric: str = "input"):
    """Aggregate input throughput from whichever export shape this build wrote."""
    aggregate = run_dir / "profile_export_aiperf.json"
    if aggregate.is_file():
        value = json.loads(aggregate.read_text()).get(f"{metric}_token_throughput")
        return value.get("avg") if isinstance(value, dict) else value
    for name in ("profile_export.jsonl", "profile_export.json"):
        path = run_dir / name
        if not path.is_file():
            continue
        tokens = 0
        seconds: list[float] = []
        for line in path.read_text().splitlines():
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            tokens += rec.get("input_token_count") or 0
            start, end = rec.get("request_start_time"), rec.get("request_end_time")
            if start is not None and end is not None:
                seconds.append(float(end) - float(start))
        if tokens and seconds:
            return tokens / max(seconds)      # window span, not sum of latencies
    return None


def redacted(cmd: list[str], token: str | None) -> str:
    return " ".join(shlex.quote("[REDACTED]" if token and part == token else part)
                    for part in cmd)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", required=True, help="base URL, e.g. https://host:8000")
    ap.add_argument("--model", required=True, help="served model id")
    ap.add_argument("--endpoint", default="/v1/chat/completions")
    ap.add_argument("--token-env", default="APIKEY",
                    help="environment variable holding the bearer key (never an argument)")
    ap.add_argument("--grid", default=DEFAULT_GRID)
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--window-s", type=int, default=60)
    ap.add_argument("--metric", choices=("input", "output"), default="input",
                    help="which throughput the profile is judged on: prefill reads input, "
                         "decode and balanced read output")
    ap.add_argument("--input-tokens", type=int, default=2048)
    ap.add_argument("--output-tokens", type=int, default=8,
                    help="keep small: this measures input (prefill/encode) throughput")
    ap.add_argument("--book", default="", help="plain-text book for unique prompts")
    ap.add_argument("--book-skip-head", type=int, default=None)
    ap.add_argument("--num-dataset-entries", type=int, default=4000)
    ap.add_argument("--prompts-needed", type=int, default=4000)
    ap.add_argument("--warmup-prompts", type=int, default=400)
    ap.add_argument("--max-served-pct", type=float, default=cold_gate.__dict__.get("DEFAULT_MAX", 2.0))
    ap.add_argument("--allow-anonymous", action="store_true",
                    help="declare that the endpoint needs no credential; never send a key invented to satisfy this tool")
    ap.add_argument("--tokenizer", default="",
                    help="tokenizer path or id for length control; omit to use the build default")
    ap.add_argument("--request-timeout-s", type=int, default=1800)
    ap.add_argument("--aiperf", default="aiperf")
    ap.add_argument("--auth-flag", default="",
                    help="override the detected credential flag (e.g. --custom-auth-header)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--plan", action="store_true",
                    help="print the exact commands and exit without measuring")
    args = ap.parse_args()

    out = pathlib.Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    grid = [int(x) for x in args.grid.split(",") if x.strip()]
    token = env(args.token_env)
    if args.plan:
        if not getattr(args, "_vocab", None):
            ok, detail, vocab, auth_flag = probe(args.aiperf, needs_corpus=bool(args.book))
            args._vocab = vocab or "classic"
            if not ok:
                print(f"# probe note: {detail}")
        inputs = None
        for concurrency in grid:
            for rep in range(1, args.reps + 1):
                print(redacted(command(args, out / f"c{concurrency:03d}" / f"r{rep}",
                                       concurrency, 600_000 + concurrency * 1000 + rep,
                                       inputs, args.auth_flag or "--api-key", token), token))
        print(f"# {len(grid) * args.reps} measured runs; token from ${args.token_env}: "
              f"{'set' if token else 'NOT SET'}")
        return 0

    if not token and not args.allow_anonymous:
        print(f"REFUSED: credential env ${args.token_env} is unset. Set it, or pass "
              "--allow-anonymous if the endpoint genuinely needs no credential. Never pass a "
              "key as an argument (it lands in ps and shell history) and never invent one.",
              file=sys.stderr)
        return 2
    ok, detail, vocab, auth_flag = probe(args.aiperf, needs_corpus=bool(args.book))
    args._vocab = vocab or "classic"
    if args.auth_flag:
        auth_flag = args.auth_flag
    if not ok:
        print(f"REFUSED: {detail}", file=sys.stderr)
        return 2
    args._auth_flag_used = auth_flag          # recorded by name only, never by value
    print(f"probe: {detail}")

    # Every measured run gets its own slice of the corpus. The benchmark tool restarts its
    # dataset cursor for each invocation, so repetitions replay the same passages and measure the
    # prefix cache: three times the pool changed nothing (53.3%, then 53.8% served in repetition 3
    # with 1,944 unique prompts and 672 cumulative requests). Slices are laid out end to end at the
    # measured cost of a 2,048-token passage in this corpus -- 50,000 characters -- so no two runs
    # can share a prefix, and each run's pool is kept under its own name as evidence.
    def pool_consumed_chars(corpus_path):
        """Characters of source text a built pool actually drew on."""
        try:
            return sum(len(json.loads(l)["prompt"])
                       for l in corpus_path.read_text().split("\n") if l.strip())
        except (OSError, ValueError, KeyError):
            return 0

    # The slice cursor is DERIVED from the campaign directory, not kept in a side file: a
    # campaign interrupted by corpus exhaustion, an outage or a session drop is resumed by
    # running the same command into the same --out, and the sequence of prompt slices must
    # continue where it stopped. A separate cursor file could disagree with the evidence;
    # these manifests are the evidence.
    base_skip = args.book_skip_head if args.book_skip_head is not None else 20_000
    prior = 0
    for man in sorted(out.glob("corpus-*-manifest.json")):
        corpus = man.with_name(man.name.replace("-manifest.json", ".jsonl"))
        try:
            skipped = int(json.loads(man.read_text())["skipped_head_chars"])
        except (OSError, ValueError, KeyError):
            continue
        prior = max(prior, skipped + int(pool_consumed_chars(corpus) * 1.15) + 1)
    if prior > base_skip:
        base_skip = prior
        print(f"  resuming: {len(list(out.glob('corpus-*-manifest.json')))} pool(s) already "
              f"consumed; next slice starts at character {base_skip:,}")
    slice_index = 0
    inputs, corpus_manifest = (None, {})

    def cut(tag: str):
        """Cut the next disjoint slice, advancing by the bytes the PREVIOUS slice really used.

        The stride used to be passages x 50,000 characters -- my estimate of a 2,048-token
        passage -- which over-reserves by ~3x: nine runs in, and the third C32 slice already
        started at 90 MB of a 105 MB corpus, so an eight-point grid would have refused itself for
        arithmetic reasons rather than measurement ones. Advancing by the produced pool's actual
        text length plus 15% headroom keeps slices disjoint and makes the corpus budget real.
        """
        nonlocal base_skip
        args.book_skip_head = base_skip
        inputs, manifest = build_inputs(args, out, tag=tag)
        consumed = sum(len(json.loads(l)["prompt"])
                       for l in inputs.read_text().split("\n") if l.strip())
        base_skip += int(consumed * 1.15) + 1
        return inputs, manifest
    summary: list[dict] = []
    # Pool size must be derived from the workload, not chosen. A pool smaller than the requests
    # the window issues is recycled by the sampler, and the recycled part measures the prefix
    # cache -- seen as a warm repetition running ~27% faster than the honest cold one. So: one
    # automatic re-size computed from the run's own completed-request count, then retry that
    # repetition once. Still not cold means the campaign halts, as before.
    resized = False
    for concurrency in grid:
        for rep in range(1, args.reps + 1):
            for attempt in (1, 2):
                run_dir = out / f"c{concurrency:03d}" / f"r{rep}"
                run_dir.mkdir(parents=True, exist_ok=True)
                if args.book:
                    inputs, corpus_manifest = cut(f"c{concurrency:03d}-r{rep}")
                cmd = command(args, run_dir, concurrency, 600_000 + concurrency * 1000 + rep,
                              inputs, auth_flag, token)
                (out / "commands.log").open("a").write(redacted(cmd, token) + "\n")
                rc = run(cmd, run_dir / "run.log", token)
                fraction, issued, reason = cold_gate.served_fraction(run_dir)
                served = None if fraction is None else round(100.0 * fraction, 3)
                verdict = ("unknown" if served is None
                           else "cold" if served <= args.max_served_pct else "warm")
                if (verdict == "warm" and not resized and inputs is not None and issued
                        and attempt == 1):
                    # Monotonic, and sized for the whole campaign. The first version computed
                    # issued x 1.5 + warm-up from ONE window's completed requests (128) and asked
                    # for 392 -- smaller than the 400 it was replacing. The cursor advances across
                    # repetitions, so consumption is cumulative: size for every rep, never shrink,
                    # and leave headroom because shared prefixes in any real corpus also register
                    # as cache reads (1.2% served with a fresh pool).
                    needed = max(int(args.num_dataset_entries * 2),
                                 int(issued * args.reps * 2) + args.warmup_prompts * 2)
                    print(f"  pool under-sized: {args.num_dataset_entries} unique prompts held "
                          f"{issued} requests in one window; rebuilding at {needed} and retrying "
                          f"C{concurrency} r{rep} once (R-03-28)")
                    # Advance the cut. Re-building from the same source at the same offset
                    # produces passages that OPEN with the same text as the pool being replaced,
                    # so the "bigger" pool shares long prefixes with what the cache already
                    # holds -- measured on this very host as 5.2% and 23.5% served after a
                    # re-size. Skip past the consumed range; if the source cannot supply a
                    # disjoint range, make_book_corpus refuses and nothing is measured.
                    base_skip = args.book_skip_head + int(
                        pool_consumed_chars(
                            out / f"corpus-c{concurrency:03d}-r{rep}.jsonl") * 1.15) + 1
                    args.num_dataset_entries = needed
                    args.prompts_needed = needed   # the cutter reads this name
                    resized = True
                    continue
                break
            throughput = throughput_from(run_dir, args.metric)
            row = {"concurrency": concurrency, "repetition": rep, "exit": rc,
                   f"{args.metric}_tokens_per_s": throughput, "served_prompt_pct": served,
                   "requests_issued": issued, "cache_verdict": verdict,
                   "reason_for_unknown": reason, "pool_resized": resized,
                   "pool_records": (int(args.prompts_needed + args.warmup_prompts)
                                    if args.book else None),
                   "pool_skip_head": args.book_skip_head if args.book else None}
            summary.append(row)
            print(f"  C{concurrency:<4} r{rep}  "
                  f"{('%.1f tok/s' % throughput) if throughput else 'no result':>13}"
                  f"  served={served if served is not None else 'n/a'}%  {verdict}")
            if verdict != "cold":
                detail = (f"C{concurrency} r{rep}: measured "
                          f"{served if served is not None else 'no'}% prefix-cache served "
                          f"(limit {args.max_served_pct}%).")
                if issued:
                    detail += (f" The window issued {issued} requests against a pool of "
                               f"{args.num_dataset_entries} unique prompts"
                               + (" (already re-sized once; no further automatic growth)"
                                  if resized else "")
                               + "; a pool smaller than the request count is recycled and "
                                 "measures the cache, not the engine.")
                (out / "INVALID.cold-cache").write_text(
                    detail + " Warm runs are not reportable as prefill capacity "
                    "(R-05-2, R-03-28).\n")
                _write(out, args, summary, corpus_manifest, halted=True)
                return 1
    _write(out, args, summary, corpus_manifest, halted=False)
    return 0


def auth_flag_placeholder(args):
    """Name the credential flag used, never its value."""
    return getattr(args, "_auth_flag_used", args.auth_flag or "detected-at-probe")


def _write(out: pathlib.Path, args, summary: list[dict], manifest: dict, *, halted: bool) -> None:
    cold = [r for r in summary if r["cache_verdict"] == "cold"]
    per_point: dict[int, list[float]] = {}
    field = f"{args.metric}_tokens_per_s"
    for row in cold:
        if row[field]:
            per_point.setdefault(row["concurrency"], []).append(row[field])
    import statistics
    result = {
        "schema_version": 1,
        "kind": "cold-prefill-sweep",
        "generated_utc": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "url": args.url, "model": args.model, "endpoint": args.endpoint,
        "credential": {"source": f"env ${args.token_env}", "flag": auth_flag_placeholder(args),
                       "value_recorded": False},
        "input": {"book": args.book or None, "corpus_manifest": manifest,
                  "num_dataset_entries_when_synthetic": args.num_dataset_entries},
        "cold_limit_served_pct": args.max_served_pct,
        "runs": summary,
        "halted": halted,
        f"cold_{args.metric}_tokens_per_s_by_concurrency": {
            str(c): {"median": statistics.median(v), "n": len(v), "min": min(v), "max": max(v)}
            for c, v in sorted(per_point.items())},
        "claim_permitted": (not halted) and bool(per_point),
        "note": ("only cold-verdict runs contribute to the summary; a sweep that halted yields "
                 "no headline (R-03-28)."),
    }
    (out / "result.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    digest = hashlib.sha256((out / "result.json").read_bytes()).hexdigest()
    (out / "SHA256SUMS").write_text(f"{digest}  result.json\n")
    print(f"  result: {out / 'result.json'}")
    print(f"  cold points: {len(per_point)}  halted: {halted}  sha256: {digest[:16]}")


if __name__ == "__main__":
    sys.exit(main())
