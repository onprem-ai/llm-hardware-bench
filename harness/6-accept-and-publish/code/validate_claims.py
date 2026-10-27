#!/usr/bin/env python3
"""R-PIPE-2: every stated delta must resolve to an artifact and recompute.

The comparator registry stores ADDRESSES, never numbers. Values are read from the
artifact at check time, so a registry entry cannot silently disagree with the
publication it points at, and a claim cannot quote a remembered figure.

Usage:
  harness/6-accept-and-publish/code/validate_claims.py CLAIMS.yaml [CLAIMS.yaml ...]
  harness/6-accept-and-publish/code/validate_claims.py --self-test
"""
import json, pathlib, statistics, sys

import pathlib
ROOT = next(a for a in pathlib.Path(__file__).resolve().parents
           if (a / '.git').exists())


def load_registry(path=None):
    """Load the comparator registry.

    Per-host baselines are instance data: they live beside their study at
    results/<host>/comparators.json and are all discovered and merged here.
    `path` overrides discovery (used by --self-test with the clearly-toy
    example under code/examples/).
    """
    if path:
        paths = [pathlib.Path(path)]
    else:
        paths = sorted(ROOT.glob("results/*/comparators.json"))
        if not paths:
            raise SystemExit("no comparator registry found under results/*/comparators.json "
                             "(per-host baselines live beside their study)")
    out, dup = {}, []
    for p in paths:
        reg = json.loads(pathlib.Path(p).read_text())
        for c in reg.get("comparators", []):
            cid = c.get("id")
            if not cid:
                raise SystemExit(f"comparator entry without id in {p}")
            if cid in out:
                dup.append(cid)
            out[cid] = c
    if dup:
        raise SystemExit(f"duplicate comparator ids: {sorted(set(dup))}")
    return out


def resolve(entry):
    """Follow artifact + dotted field path to a number. Fails loudly if absent.

    A numeric path segment indexes into a list (e.g.
    `normalized_data.series.decode.points.1.throughput.median`), so a series point
    can be a comparator without copying its value out of the artifact.
    """
    art = ROOT / entry["artifact"]
    if not art.is_file():
        raise LookupError(f"artifact missing: {entry['artifact']}")
    node = json.loads(art.read_text())
    for part in entry["field"].split("."):
        if isinstance(node, list):
            try:
                node = node[int(part)]
                continue
            except (ValueError, IndexError):
                raise LookupError(f"index {part!r} does not resolve in {entry['artifact']}")
        if not isinstance(node, dict) or part not in node:
            raise LookupError(f"field {entry['field']} not in {entry['artifact']}")
        node = node[part]
    if not isinstance(node, (int, float)):
        raise LookupError(f"{entry['id']} resolved to non-numeric {type(node).__name__}")
    return float(node)


def validate(path, registry_path=None):
    """Return (errors, infos) for one claims file."""
    import yaml
    errs, infos = [], []
    claims = yaml.safe_load(pathlib.Path(path).read_text())
    reg = load_registry(registry_path)

    head = claims.get("headline") or {}
    reps = head.get("repetition_values") or []
    if reps and head.get("value") is not None:
        med = statistics.median(reps)
        if abs(med - float(head["value"])) > 0.02:
            errs.append(f"headline.value {head['value']} is not the median of "
                        f"repetition_values ({med:.2f}). Stated headline must be derivable "
                        f"from the listed repetitions.")
    if reps and len(reps) < 3:
        errs.append(f"headline has {len(reps)} repetitions; protocol grade requires >=3.")
    if head.get("provisional"):
        if not str(head.get("provisional_reason", "")).strip():
            errs.append("headline.provisional is true but provisional_reason is empty.")
    else:
        infos.append("headline is NOT marked provisional - verify chapter 4/5 completion "
                     "and prompt-source conformance before publishing.")

    banned = {c.get("id") for c in claims.get("prohibited_claims") or []}
    for c in claims.get("claims") or []:
        cid = c.get("id", "<unnamed>")
        for bad in ("comparator_value", "comparator_stated_value", "baseline_value"):
            if bad in c:
                errs.append(f"claim {cid} carries its own comparator value in '{bad}'. "
                            f"Comparators must be referenced by id (R-PIPE-2).")
        if cid in banned:
            errs.append(f"claim {cid} is also listed in prohibited_claims - contradiction.")
        ref = c.get("comparator")
        if ref not in reg:
            errs.append(f"claim {cid} references unknown comparator '{ref}'. It is not a "
                        f"comparator until it resolves to an artifact field.")
            continue
        entry = reg[ref]
        try:
            base = resolve(entry)
        except LookupError as e:
            errs.append(f"claim {cid}: {e}")
            continue
        subj = c.get("subject_value")
        if not isinstance(subj, (int, float)):
            errs.append(f"claim {cid} has no numeric subject_value")
            continue
        pct = (float(subj) - base) / base * 100.0
        stated = c.get("stated_pct")
        tol = float(c.get("tolerance_pct", 0.5))
        if not isinstance(stated, (int, float)):
            errs.append(f"claim {cid} has no stated_pct")
        elif abs(pct - float(stated)) > tol:
            errs.append(f"claim {cid} states {stated}% but recomputes to {pct:+.2f}% "
                        f"against {ref} = {base:.3f} ({entry['artifact']} :: {entry['field']}). "
                        f"Either the claim or the comparator is wrong.")
        if c.get("direction") == "higher_is_better" and pct < 0:
            errs.append(f"claim {cid} claims improvement but recomputes to {pct:+.2f}%")
        if float(entry.get("concurrency", -1)) != float(head.get("concurrency", -2)):
            infos.append(f"claim {cid}: comparator is at C{entry.get('concurrency')}, "
                         f"headline at C{head.get('concurrency')} - cross-configuration, "
                         f"must be disclosed in the note")
        if entry.get("unit") != head.get("metric"):
            errs.append(f"claim {cid} compares {entry.get('unit')} against headline "
                        f"metric {head.get('metric')}")
    for p in claims.get("prohibited_claims") or []:
        if not str(p.get("reason", "")).strip():
            errs.append(f"prohibited claim {p.get('id')} has no reason recorded")
    return errs, infos


def main():
    args = sys.argv[1:]
    if args == ["--self-test"]:
        import subprocess, tempfile, yaml
        toy_reg = ROOT / "harness/6-accept-and-publish/code/examples/comparators.toy.json"
        reg = load_registry(toy_reg)
        toy = yaml.safe_load((ROOT / "harness/6-accept-and-publish/code/examples/claims.toy.yaml").read_text())
        print(f"toy registry: {len(reg)} comparators, all resolving:")
        for cid, e in reg.items():
            print(f"   {cid} = {resolve(e):.3f}")
        cases = []
        cases.append(("valid claims file", toy, True))
        bad = json.loads(json.dumps(toy))
        bad["claims"][0]["comparator"] = "toy-model.decode.phantom-1111"
        cases.append(("phantom comparator (the 2026-09-06 error)", bad, False))
        bad2 = json.loads(json.dumps(toy))
        bad2["claims"][0]["stated_pct"] = 15.0
        cases.append(("delta mis-stated as 15%", bad2, False))
        bad3 = json.loads(json.dumps(toy))
        bad3["headline"]["value"] = 1150.0
        cases.append(("headline not the median of its repetitions", bad3, False))
        bad4 = json.loads(json.dumps(toy))
        bad4["claims"][0]["comparator_value"] = 1111.0
        cases.append(("claim supplying its own comparator value", bad4, False))
        bad5 = json.loads(json.dumps(toy))
        bad5["claims"][0]["id"] = "toy-model.prefill.improvement"
        cases.append(("claim that is also prohibited", bad5, False))
        ok = True
        for label, doc, expect_pass in cases:
            with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as f:
                yaml.safe_dump(doc, f)
                name = f.name
            errs, _ = validate(name, registry_path=toy_reg)
            got = not errs
            verdict = "PASS" if got else "FAIL"
            good = got == expect_pass
            ok &= good
            print(f"  [{'ok' if good else 'BAD'}] {label:<48} -> {verdict}"
                  + (f"  ({errs[0][:70]})" if errs and not got else ""))
        print("self-test:", "OK" if ok else "BROKEN")
        return 0 if ok else 1

    if not args:
        print(__doc__)
        return 2
    bad = 0
    for path in args:
        errs, infos = validate(path)
        for e in errs:
            print(f"  ERROR {path}: {e}")
        for i in infos:
            print(f"  info  {path}: {i}")
        print(f"{'PASS' if not errs else 'FAIL'}  {path}  ({len(errs)} errors)")
        bad += bool(errs)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
