#!/usr/bin/env python3
"""Repository integrity check for the pipeline restructure.

Mechanises the failure modes that this repo has actually hit:
  1. a rule with no owner (two documents state it, they drift);
  2. a reference deleted while its target still existed, or a target moved while
     references stayed (dangling links found three times on 2026-09-06);
  3. a comparator that resolves to nothing (the 1111 tok/s error);
  4. a document growing back the text it was supposed to shed.

Debt is baselined: the check is green when there is no NEW violation, so the
restructure can proceed chapter by chapter without a wall of pre-existing noise.

  harness/check_repo.py                 # fail on new violations
  harness/check_repo.py --update-baseline   # accept current state as the floor
  harness/check_repo.py --full          # report all violations, baseline ignored
"""
import hashlib, json, pathlib, re, subprocess, sys

import pathlib
ROOT = next(a for a in pathlib.Path(__file__).resolve().parents
           if (a / '.git').exists())
BASE = pathlib.Path(__file__).resolve().parent / "repo-check-baseline.json"
VALID_KINDS = {"rule", "record"}
VALID_STEPS = {"1", "2", "3", "4", "5", "6", "7", "cross", "produced-by"}

SKIP_PARTS = {".git", "node_modules", ".pytest_cache", "dist", ".astro"}


def tracked(rel=None):
    """Tracked plus untracked-but-not-ignored files.

    A document an agent has just written is the most likely place for a new violation and is not
    in `git ls-files` yet. Two earlier versions got this wrong: one added untracked files only when
    `rel` named a directory, so callers passing a pattern like "*.md" scanned tracked files only;
    another tried to add a pathspec and silently matched nothing. Asking git for `--cached
    --others --exclude-standard` fixes both and honours .gitignore, which keeps the multi-gigabyte
    evidence cache out of every sweep without a hand-listed skip set.
    """
    args = ["git", "-C", str(ROOT), "ls-files", "--cached", "--others", "--exclude-standard"]
    if rel:
        args.append(rel)
    out = subprocess.run(args, capture_output=True, text=True).stdout.split()
    return [p for p in dict.fromkeys(out) if not any(s in p for s in SKIP_PARTS)]


PIPELINE_MAX_LINES = 200   # the cap on the governing document; substance belongs in a chapter

# Precision, size, topology and campaign parameters are measurement conditions, not part of a
# model's name. They already have fields - repository, revision, quantization, deployment - and
# the publication label becomes the page <h1>, <title> and the JSON-LD name. See R-06-12.
QUANTISATION_TOKENS = ("NVFP4", "MXFP4", "FP4", "FP8", "BF16", "W4A4", "W8A8",
                       "INT4", "INT8", "AWQ", "GPTQ", "GGUF")
SIZE_CONDITION_WORDS = ("full model", "full", "quantized", "quantised", "pruned", "sparse")


def model_name_decorated(name):
    """Return why *name* is not a bare model name, or None if it is one.

    Words that are genuinely part of a product name ("Flash", "Next") and version or date tokens
    are allowed. What is not allowed is a name carrying measurement conditions - a parenthetical,
    a precision suffix, or a serving-parameter value - because those change per deployment while
    the model's identity does not, and because the deployment conditions are already recorded
    beside the model in every publication and report config.
    """
    if not isinstance(name, str) or not name.strip():
        return "empty or missing"
    if "(" in name or ")" in name:
        return "carries a parenthetical qualifier"
    upper = name.upper()
    for token in QUANTISATION_TOKENS:
        if re.search(r"\b" + token + r"\b", upper):
            return "carries the precision token " + repr(token)
    lowered = name.lower()
    for word in SIZE_CONDITION_WORDS:
        if re.search(r"\b" + word + r"\b", lowered):
            return "carries the size/condition word " + repr(word)
    if re.search(r"\bseq\d+\b|\bgraph\d+\b|\bmtp-?\d+\b|\bc\d+\b", name, re.I):
        return "carries a serving-parameter value"
    return None



def front(text):
    """Minimal front-matter reader: kind: X / step: Y / produced_by: Z."""
    if not text.startswith("---"):
        return {}
    block = text.split("---", 2)[1] if text.count("---") >= 2 else ""
    return dict(re.findall(r"^(\w+):\s*(.+?)\s*$", block, re.M))


# Ownership is DERIVED from the path, never declared in a table. A hand-maintained map here
# named only steps 2 and 5, still listed a docs/ file deleted today, and so missed a chapter
# being overwritten with another chapter's text - it caught that by luck of which steps it
# happened to mention. The pipeline's shape is the only input below.
# Two root rule documents by design: PIPELINE.md governs the pipeline, README.md introduces the
# repository. Everything else is owned by a step directory. Do not add to this set: a new entry
# means a new ungoverned authority, which is how PROCEDURE.md and PIPELINE.md came to describe
# the same thing twice.
CROSS_STEP_DOCS = {"PIPELINE.md", "CLAUDE.md", "README.md", "harness/MOVED.md"}
STEP_DIR_NAME = re.compile(r"^\d-")
STEP_DIR = re.compile(r"^harness/(\d)-[^/]+/(.+)$")


def declared_owner(p: str, kind, step):
    """Expected (kind, step) for a document, derived from where it lives.

    - Root instruction documents and MOVED.md are cross-step.
    - A rule document under harness/<n>-*/ belongs to step n. Code and test trees hold
      component READMEs whose owner is the artifact they describe, so they are exempt.
    - Anything else is a record or component doc: not owned by a chapter rule at all.
    """
    if p in CROSS_STEP_DOCS:
        return ("rule", "cross")
    m = STEP_DIR.match(p)
    if not m or kind != "rule":
        return None
    n, rest = m.group(1), m.group(2)
    if rest.split("/")[0] in ("code", "tests", "schemas") or not rest.endswith(".md"):
        return None
    return ("rule", n)
# Everything under these prefixes is a record or a component README: exempt from the
# front-matter requirement, because their owner is the artifact or the code they describe.
# A document under code/ or tests/ is owned by the code it describes: it travels with
# that code and is not a procedure document needing a chapter owner.
CODE_DOC_MARKERS = ("/code/", "/tests/")


def sizes_over(root, files, ceiling):
    """Tracked files above the size ceiling; unreadable entries are skipped, not fatal."""
    out = []
    for f in files:
        try:
            size = (root / f).stat().st_size
        except OSError:
            continue
        if size > ceiling:
            out.append((f, size))
    return out


def is_code_doc(p: str) -> bool:
    return any(m in f"/{p}" for m in CODE_DOC_MARKERS)


# Records are owned by the thing they describe, not by a chapter. Everything else that is
# markdown must answer for an owner. Only two prefixes qualify: study evidence (including the
# ignored cache and retired copies) and the code/test trees of a step, whose docs belong to the
# artifact next to them. A stale listing of former top-level directories lived here; those
# directories are gone, so the rule is derived from the step layout instead of remembered.
def is_record_path(p: str) -> bool:
    if p.startswith("results/"):
        return True
    m = STEP_DIR.match(p)
    return bool(m and m.group(2).split("/")[0] in ("code", "tests", "schemas", "examples"))


def instruction_docs():
    return [p for p in sorted(set(tracked("*.md")))
            if (ROOT / p).is_file() and not is_record_path(p)
            and (p.count("/") == 0 or p.startswith("harness/"))]


def check():
    viol = []

    # 1. Ownership: every instruction doc declares kind and step.
    for p in instruction_docs():
        if is_code_doc(p):
            continue
        if not (ROOT / p).is_file():
            continue          # already reported by the link pass
        body = (ROOT / p).read_text(errors="ignore")
        fm = front(body)
        kind = fm.get("kind")
        if kind == "pointer" or "kind: pointer" in body[:400]:
            if not re.search(r"\]\((?!http)[^)]+\)", body):
                viol.append(f"dead-pointer {p}: kind: pointer with no link to its new home")
            continue
        want = declared_owner(p, kind, fm.get("step"))
        if want and (kind, fm.get("step")) != want:
            viol.append(f"wrong-owner {p}: declared ({kind},{fm.get('step')}), "
                        f"expected {want[0]}/{want[1]}")
            continue
        if kind not in VALID_KINDS:
            viol.append(f"unowned-doc {p}: kind={kind!r} (must be rule|record)")
            continue
        if kind == "rule":
            step = fm.get("step")
            if step not in VALID_STEPS:
                viol.append(f"rule-without-owner {p}: step={step!r} (1..7|cross)")
        elif not fm.get("produced_by") and fm.get("step") not in VALID_STEPS:
            viol.append(f"record-without-producer {p}: add produced_by: <step>")

    # 2. Pipeline structure: seven chapters, each with a RULES.md.
    for n in range(1, 8):
        hits = list((ROOT / "harness").glob(f"{n}-*/RULES.md"))
        if len(hits) != 1:
            viol.append(f"chapter-{n}-rules: expected exactly 1 RULES.md, found {len(hits)}")

    # 3. Dangling relative links in tracked markdown.
    # Capture the whole target, including spaces: a target containing spaces is
    # invalid markdown, and truncating at whitespace hides exactly that class of
    # breakage (found: a link mangled by an automated reference rewrite).
    link = re.compile(r"\[[^\]]*\]\(([^)]+)")
    for p in tracked("*.md") + tracked("docs") + tracked("harness") + tracked("reports"):
        if not p.endswith(".md") or any(s in p for s in SKIP_PARTS):
            continue
        # A path in the index that is absent from the worktree is exactly the kind of
        # drift this check exists for (a move that deleted without staging). Report it;
        # do not crash on it.
        if not (ROOT / p).is_file():
            viol.append(f"missing-in-worktree {p}: tracked by git but absent on disk "
                        f"(index and worktree disagree)")
            continue
        for m in link.finditer((ROOT / p).read_text(errors="ignore")):
            tgt = m.group(1).strip().strip('`').strip()
            if " " in tgt and not tgt.startswith(("http", "#")):
                viol.append(f"malformed-link {p}: target contains spaces -> ({tgt})")
                continue
            if tgt.startswith(("http", "mailto:", "#", "/")) or "<" in tgt or ">" in tgt:
                continue
            tgt = tgt.split("#")[0]
            if tgt and not (ROOT / p).parent.joinpath(tgt).resolve().exists() \
               and not (ROOT / tgt).exists():
                viol.append(f"dangling-link {p}: -> {tgt}")

    # 4. Rule IDs defined in exactly one file (a definition cites sources; a
    #    reference just names the ID).
    defs = {}
    for p in instruction_docs():
        for rid in re.findall(r"^(#{2,6})\s+`?(R-(?:[A-Z]+|\d{2})-\d+)`?(?:\s|—|$)", (ROOT / p).read_text(errors="ignore"), re.M):
            defs.setdefault(rid, []).append(p)
    for rid, where in sorted(defs.items()):
        if len(set(where)) > 1:
            viol.append(f"duplicate-rule-definition {rid}: defined in {sorted(set(where))}")

    # 4b. Every legacy section tracked in MOVED.md must still exist in some file.
    #     A move that loses a paragraph is worse than no move: the rule reads as
    #     having been retired deliberately.
    if (ROOT / "harness" / "MOVED.md").is_file():
        corpus = ""
        for q in list((ROOT / "harness").rglob("*.md")) + list((ROOT / "results").rglob("*.md")) \
                + list((ROOT / "docs").rglob("*.md")) + list((ROOT / "reports").rglob("*.md")):
            if q.is_file():
                corpus += q.read_text(errors="ignore") + "\n"
        for title in re.findall(r"^\| (.+?) \| ([0-9]+) \|",
                                (ROOT / "harness" / "MOVED.md").read_text(), re.M):
            key = re.sub(r"^#+\s*", "", title[0].replace("\\|", "|")).strip()
            key = re.sub(r"\s+\u2014\s+moved$", "", key).strip()
            if key and key not in corpus:
                viol.append(f"lost-section: '{key}' is tracked in MOVED.md but exists nowhere")

    # 4c. A pointer stub must stay a stub, or it has quietly become a second owner.
    for p in instruction_docs():
        if is_code_doc(p):
            continue
        if not (ROOT / p).is_file():
            continue          # already reported by the link pass
        body = (ROOT / p).read_text(errors="ignore")
        if "kind: pointer" in body[:400]:
            n = len(body.splitlines())
            if n > 30:
                viol.append(f"pointer-drift {p}: {n} lines - a pointer must be <= 30, "
                            f"content belongs to its owning chapter")

    # 4d. Every chapter file must actually own rules.
    for n in range(1, 8):
        for f in (ROOT / "harness").glob(f"{n}-*/RULES.md"):
            ids = set(re.findall(r"^#{2,4}\s+(R-\d{2}-\d+)", f.read_text(errors="ignore"), re.M))
            if not ids:
                viol.append(f"chapter-{n}-no-rule-ids: {f.name} defines no R-{n:02d}-N rules")

    # 4e. The governing document stays short enough to be read whole.
    cap = PIPELINE_MAX_LINES
    pl = len((ROOT / "PIPELINE.md").read_text(errors="ignore").splitlines()) if (ROOT / "PIPELINE.md").is_file() else 0
    if pl > cap:
        viol.append(f"pipeline-too-long {pl} lines > cap {cap}: move substance into a chapter RULES.md")

    # 4f. An ignored evidence cache must be declared, and nothing that big may be tracked.
    #     The cache exists because gigabytes cannot live in git; the failure mode is either
    #     committing it anyway or letting it sit there undeclared and unaccounted for.
    SIZE_CEILING = 5 * 1024 * 1024
    # Only files git actually tracks. `tracked()` deliberately includes untracked files so a
    # brand-new doc cannot dodge the ownership checks; using it here would flag the whole
    # deliberately-ignored evidence cache on every run.
    in_git = subprocess.run(["git", "-C", str(ROOT), "ls-files"], capture_output=True, text=True).stdout.split()
    oversized = list(sizes_over(ROOT, in_git, SIZE_CEILING))
    # Versioned benchmark INPUTS -- a prompt corpus and its provenance -- are the one kind of
    # tracked payload allowed above the documentation ceiling. The allowance is path-scoped,
    # per-file capped and total capped, because "we allow a dataset" must not be able to become
    # "we allow anything". Raw run evidence still belongs in the ignored evidence cache.
    import fnmatch as _fm
    DATASET_PATTERNS = ("harness/*/data/*",)
    DATASET_FILE_CEILING = 64 * 1024 * 1024
    DATASET_TOTAL_BUDGET = 100 * 1024 * 1024
    def _is_dataset(path):
        return any(_fm.fnmatch(path, pat) for pat in DATASET_PATTERNS)
    ds = [(f, s) for f, s in oversized if _is_dataset(f)]
    for f, s in ds:
        if s > DATASET_FILE_CEILING:
            viol.append(f"dataset-file-too-large {f}: {s // 1024} KiB > "
                        f"{DATASET_FILE_CEILING // 1024} KiB versioned-input ceiling")
    ds_total = sum(s for _, s in ds)
    if ds_total > DATASET_TOTAL_BUDGET:
        viol.append(f"dataset-total-too-large: {ds_total // 1024} KiB tracked > "
                    f"{DATASET_TOTAL_BUDGET // 1024} KiB budget")
    for f, size in [(f, s) for f, s in oversized if not _is_dataset(f)]:
        viol.append(f"tracked-file-too-large {f}: {size // 1024} KiB > "
                    f"{SIZE_CEILING // (1024 * 1024)} MiB ceiling "
                    f"(raw evidence belongs in _local-evidence/, untracked)")
    for cache in (ROOT / "studies").glob("*/_local-evidence") if (ROOT / "studies").is_dir() else []:
        manifest = cache.parent / "EVIDENCE.md"
        if not manifest.is_file():
            viol.append(f"undeclared-evidence-cache {cache}: no EVIDENCE.md beside it")
            continue
        text = manifest.read_text(errors="ignore")
        for sub in sorted(p.name for p in cache.iterdir() if p.is_dir()):
            # Declared means a table row naming it, not the string appearing somewhere: a manifest
            # once satisfied this by mentioning the directory inside an unrelated path.
            if sub and not re.search(rf"^\|\s*`{re.escape(sub)}`\s*\|", text, re.M):
                viol.append(f"undeclared-evidence-dir {cache.name}/{sub}: no table row in {manifest.name}")
        # A manifest that is generated from the tree cannot describe a deleted directory; a
        # hand-written one will, which is how a stale manifest keeps validating.
        declared = set(re.findall(r"^\|\s*`([A-Za-z0-9._-]+(?:/[A-Za-z0-9._-]+)*)`\s*\|", text, re.M))
        # Rows are written host-relative (`<model>/<n-step>`), while paths under the cache are
        # host-prefixed (`<hostname>/<model>/<n-step>`). Index both frames or every row looks stale.
        present = set()
        for p in (x for x in cache.rglob("*") if x.is_dir()):
            rel = p.relative_to(cache)
            present.add(str(rel))
            if len(rel.parts) > 1:
                present.add("/".join(rel.parts[1:]))
        for name in sorted(declared - present - {sub for sub in sorted(x.name for x in cache.iterdir() if x.is_dir())}):
            if name.count("/") and not any(d == name or d.startswith(name + "/") for d in present):
                viol.append(f"stale-manifest-row {manifest.name}: declares `{name}`, which does not exist")
        # The cache mirrors the record layout. Two drift modes are failures: a subtree missing
        # from the manifest, and a directory that reuses a repository top-level name, which makes
        # an evidence pile look like repo content to every reader (and to `git add -A`).
        for d in cache.rglob("*"):
            if not d.is_dir():
                continue
            name = d.name
            # Only at host and model level, where a name is read as "what kind of thing is this".
            # Below the step directory, `results/` and `logs/` are honest harness output names.
            if len(d.relative_to(cache).parts) <= 2 and not name.startswith("_unsorted") and name in {
                        "harness", "docs", "results", "tests", "published", "analysis",
                        "schemas", "runners", "collectors", "reports"}:
                viol.append(f"evidence-dir-reuses-repo-name {d.relative_to(ROOT)}: rename it; "
                            f"the cache mirrors <host>/<model>/<n-step>/, not the repo root")
            rel = d.relative_to(cache)
            # `_unsorted-*` is a declared exception: evidence pulled before the cache had a
            # shape, kept rather than guessed-at. The prefix is the admission, not a hiding
            # place - it is listed in EVIDENCE.md and every directory under it is still counted.
            if any(part.startswith("_unsorted") for part in rel.parts):
                continue
            # Only the step level is constrained. Below it, run directories keep whatever name the
            # harness gave them - constraining those would demand 1,000 renames and prove nothing.
            if len(rel.parts) == 3 and not STEP_DIR_NAME.match(rel.parts[-1]):
                viol.append(f"evidence-dir-not-a-step {d.relative_to(ROOT)}: expected '<n>-<step>/' "
                            f"under <host>/<model>/")

    # 4g. Two chapter files must not be byte-identical. A script that appends to two files in
    #     one pass once wrote chapter 3's text into chapter 5's path; ownership caught it only
    #     because the front matter disagreed. Identical bodies must fail even when they do not.
    seen = {}
    for p in sorted(x for x in tracked("*.md") if (ROOT / x).is_file() and front((ROOT / x).read_text(errors="ignore")).get("kind") == "rule"):
        digest = hashlib.sha256((ROOT / p).read_bytes()).hexdigest()
        if digest in seen and p != seen[digest]:
            viol.append(f"duplicate-chapter-content {p}: byte-identical to {seen[digest]}")
        seen.setdefault(digest, p)

    # 4h. Rules live in the pipeline tree. A rule anywhere else is an orphan chapter: nobody's
    #     step owns it, so it drifts and eventually contradicts the chapter it silently copies.
    for p in sorted(tracked("*.md")):
        if not (ROOT / p).is_file():
            continue
        fm = front((ROOT / p).read_text(errors="ignore"))
        if fm.get("kind") == "rule" and declared_owner(p, "rule", fm.get("step")) is None:
            viol.append(f"rule-outside-pipeline {p}: kind: rule with no owning step directory")

    # 4i. Repository paths cited as inline code must resolve too. Markdown links are not the only
    #     way to point at a file, and the invisible kind rots quietly: a rule cited `docs/retired/`
    #     long after docs/ was deleted, and a journal cited a raster journal under the pre-flattening
    #     path. Placeholders (`<study-id>`), globs and node-side absolute paths are exempt.
    import os
    for p in sorted(x for x in tracked("*.md") if (ROOT / x).is_file() and not is_record_path(x)):
        text = (ROOT / p).read_text(errors="ignore")
        for span in set(re.findall(r"`([^`\n]{2,120})`", text)):
            s = span.strip()
            if not re.match(r"^(?:harness|results|PIPELINE\.md|README\.md|Makefile)(?:/|$)", s):
                continue
            if any(ch in s for ch in "<>*") or s.endswith(("/", "…")) or "..." in s:
                continue
            if not (ROOT / s).exists():
                viol.append(f"stale-path-reference {p}: cites `{s}`, which does not exist")

    # 4i. Path literals in the Makefile must resolve. A Makefile has no importers: nothing but a
    #     human typing `make` discovers a stale path, so after the Astro app moved, the site target
    #     pointed at a script that no longer existed and nothing noticed.
    makefile = ROOT / "Makefile"
    if makefile.is_file():
        for m in set(re.finditer(r"\b(?:harness|results)\b(?:/[A-Za-z0-9_./-]*)?",
                                 makefile.read_text())):
            lit = m.group(0)
            start, end = m.start(), m.end()
            text = makefile.read_text()
            if (start > 0 and text[start - 1] == "-") or (end < len(text) and text[end] == "-"):
                continue   # part of a hyphenated word (a flag like --results-root), not a path
            candidate = lit.rstrip(".,")
            if not (ROOT / candidate).exists():
                viol.append(f"makefile-stale-path Makefile: references {candidate}, which does not exist")

    # 5. Comparator registries resolve. Per-host baselines are instance data: one
    #    registry lives beside each study at results/<host>/comparators.json. The
    #    instrument itself keeps only the clearly-toy example under code/examples/
    #    that its self-test resolves, and never a real host's numbers.
    registries = sorted((ROOT / "results").glob("*/comparators.json")) if (ROOT / "results").is_dir() else []
    if not registries:
        viol.append("comparator-registry-broken: no results/<host>/comparators.json found")
    toy_reg = ROOT / "harness/6-accept-and-publish/code/examples/comparators.toy.json"
    for regp in [toy_reg, *registries]:
        if not regp.is_file():
            viol.append(f"comparator-registry-broken: {regp.relative_to(ROOT)} missing")
            continue
        try:
            reg = json.loads(regp.read_text())
            for c in reg.get("comparators", []):
                node = json.loads((ROOT / c["artifact"]).read_text())
                for part in c["field"].split("."):
                    # numeric segments index into lists, mirroring validate_claims.resolve
                    if isinstance(node, list):
                        node = node[int(part)]
                    else:
                        node = node[part]
                if not isinstance(node, (int, float)):
                    viol.append(f"comparator-not-numeric {c['id']} ({regp.name})")
        except Exception as exc:
            viol.append(f"comparator-registry-broken {regp.name}: {type(exc).__name__}: {exc}")

    # 6. Claims validate wherever a claims file exists.
    for p in tracked() :
        if p.endswith("claims.yaml"):
            rc = subprocess.run([sys.executable, str(ROOT / "harness/6-accept-and-publish/code/validate_claims.py"),
                                 str(ROOT / p)], capture_output=True, text=True)
            if rc.returncode != 0:
                viol.append(f"claims-invalid {p}: {rc.stdout.strip().splitlines()[-1:]}")

    # 7. (removed) The shrinking-only ratchet on PROCEDURE.md existed to force a migration that
    #    is now complete; the file is deleted, so the ratchet and its baseline field are residue.
    #    The governing length constraint is PIPELINE.md's own cap, checked above.

    # 8. A published model label is the model name with nothing appended (R-06-12). The label is
    #    what the site renders as <h1>, <title> and the Dataset name, so decoration on this field
    #    is decoration on every page that reads it.
    for p in tracked():
        if not p.endswith("publication.json"):
            continue
        if not p.startswith("results/"):
            continue          # toy examples are not publications
        try:
            model = json.loads((ROOT / p).read_text()).get("model", {})
        except Exception:
            continue          # unreadable publications are reported by the comparator pass
        reason = model_name_decorated(model.get("name", ""))
        if reason:
            viol.append(f"model-name-decorated {p}: model.name {model.get('name')!r} {reason}; "
                        "name the model, keep conditions in model.quantization")

    # 9. A publication must carry its own reproduction record (pinned container,
    #    model pin, verbatim launch commands, client, corpus) and a procedure
    #    digest. The site renders both sections, so a publication without them
    #    publishes numbers nobody can re-derive, with no visible path to them.
    #    Gaps must be declared in-band (null + note), never omitted silently.
    for p in tracked():
        if not p.endswith("publication.json"):
            continue
        if not p.startswith("results/"):
            continue          # toy examples are not publications
        try:
            doc = json.loads((ROOT / p).read_text())
        except Exception:
            continue          # unreadable publications are reported by the comparator pass
        r = doc.get("reproducibility")
        if not isinstance(r, dict):
            viol.append(f"publication-without-reproducibility {p}: the site renders a Reproduce "
                        "section; add container/model/launch/client/corpus or declare the gap in-band")
            continue
        for field in ("container", "model", "launch", "client", "corpus", "source_record"):
            if field not in r:
                viol.append(f"reproducibility-missing-field {p}: {field}")
        if isinstance(r.get("container"), dict):
            for field in ("image", "engine"):
                if not r["container"].get(field):
                    viol.append(f"reproducibility-container-field {p}: {field}")
        if not isinstance(r.get("launch"), list) or not r["launch"]:
            viol.append(f"reproducibility-no-launch {p}")
        else:
            for item in r["launch"]:
                if not str(item.get("command", "")).strip():
                    viol.append(f"reproducibility-empty-command {p}: profile {item.get('profile')!r}")
        proc = doc.get("procedure")
        if not isinstance(proc, list) or len(proc) < 3:
            viol.append(f"publication-without-procedure {p}: the site renders a Procedure journal; "
                        "distill at least 3 entries (tried / failed / worked) from the study journals")

    # 10. Study files describe the LLM and the benchmark only (CLAUDE.md, "Journal
    #     scope"). Access-infrastructure details — addresses, VPN/tunnel/SSH/BMC
    #     product names and configuration — are the content class most likely to
    #     leak sensitive operational information, and they are off-topic: a host
    #     or network event is recorded by its effect on the measurement, never by
    #     its configuration. Loopback bind addresses in deployment configs are
    #     legitimate serving configuration and stay allowed.
    import re as _re
    _net_terms = _re.compile(
        r"tailnet|tailscale|\bvpn\b|openvpn|wireguard|\bipmi\b|openssh|\bsshd\b|host[- ]key",
        _re.IGNORECASE,
    )
    _ip = _re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
    _ip_allowed = {"127.0.0.1", "0.0.0.0", "255.255.255.0", "255.255.255.255"}
    for p in tracked():
        if not p.startswith("results/"):
            continue
        if not p.endswith((".md", ".json", ".yaml", ".txt", ".csv")):
            continue
        try:
            body = (ROOT / p).read_text(errors="ignore")
        except Exception:
            continue
        m = _net_terms.search(body)
        if m:
            viol.append(f"journal-network-detail {p}: access-infrastructure term {m.group(0)!r}; "
                        "record the measurement effect, not the configuration (CLAUDE.md Journal scope)")
        for m in _ip.finditer(body):
            if m.group(0) not in _ip_allowed:
                viol.append(f"journal-network-detail {p}: IP address {m.group(0)}; "
                            "record the measurement effect, not the access topology")
                break

    # 11. Host and model identifiers are instance data (2026-09-19 re-boxing:
    #     instrument in harness/, measurements in results/). They live under
    #     results/ and nowhere else: the instrument must run against any host
    #     without edits, so a host name inside harness/ is a harness that was
    #     edited for one host. Exempted: provenance prose that legitimately names
    #     the fleet (PIPELINE.md, MOVED.md, chapter RULES.md, data PROVENANCE.md),
    #     the evidence-anchored tests, the approved report reference, the
    #     generated document map, and the root front-door files that index the
    #     results. Tokens derive from the results/ tree itself -- every host
    #     directory and every model directory (recognized by carrying a digit),
    #     plus their leading segments -- so renaming a host cannot leave this
    #     rule holding stale tokens.
    def _ident(t):
        # an identifier token must look like one: >=4 chars, leading letter.
        # This is what keeps a stray numbered evidence dir or a bare digit from
        # turning every file that contains a "2" into a violation.
        return len(t) >= 4 and t[0].isalpha()

    ident_tokens = set()
    rdir = ROOT / "results"
    if rdir.is_dir():
        for host in sorted(x for x in rdir.iterdir() if x.is_dir()):
            ident_tokens.add(host.name.lower())
            ident_tokens.add(host.name.lower().split("-")[0])
            for sub in sorted(x for x in host.iterdir()
                              if x.is_dir() and any(ch.isdigit() for ch in x.name)
                              and not x.name[0].isdigit()):   # '<n>-step' dirs are not models
                ident_tokens.add(sub.name.lower())
                ident_tokens.add(sub.name.lower().split("-")[0].split(".")[0])
    ident_tokens = {t for t in ident_tokens if _ident(t)}
    ident_exempt_exact = {"README.md", "PIPELINE.md", "CONTRIBUTING.md", "CLAUDE.md", "INDEX.md"}

    def ident_exempt(p):
        if p in ident_exempt_exact:
            return True
        parts = p.split("/")
        if parts[0] == "harness":
            if p == "harness/MOVED.md":
                return True
            if len(parts) >= 3 and parts[2] == "RULES.md":
                return True
            if len(parts) >= 3 and parts[2] == "tests":
                return True
            if parts[1:] == ["3-deployment-raster", "data", "PROVENANCE.md"]:
                return True
            if parts[1:4] == ["7-report-and-feedback", "code", "reference"]:
                return True
        return False

    if ident_tokens:
        for p in tracked():
            if p.startswith("results/") or ident_exempt(p):
                continue
            try:
                body = (ROOT / p).read_text(errors="ignore").lower()
            except Exception:
                continue
            hits = sorted(t for t in ident_tokens if t in body)
            if hits:
                viol.append(f"instance-identifier-leak {p}: {hits} outside results/ - "
                            "host/model identifiers are instance data; only provenance prose "
                            "is exempt (PIPELINE.md, MOVED.md, RULES.md, tests, reference)")
    return viol


def emit_index():
    """Generate INDEX.md from the same classification the check enforces, so the
    map cannot disagree with the rule (they share one source of truth)."""
    rows = []
    for p in instruction_docs():
        if not (ROOT / p).is_file():
            continue
        fm = front((ROOT / p).read_text(errors="ignore"))
        title = fm.get("title", "")
        rows.append((p, fm.get("kind", "MISSING"), fm.get("step", "MISSING"), title))
    rec = sorted({p for p in tracked("*.md") if p.endswith(".md") and is_record_path(p)})
    lines = ["---", "kind: rule", "step: cross", "title: Document map",
             "generated-by: harness/check_repo.py --emit-index", "---", "",
             "# Document map", "",
             "Two kinds, no third category: **rule** (normative, exactly one owner) and",
             "**record** (evidence, append-only). Ownership is enforced by",
             "`harness/check_repo.py`; a `MISSING` below is a bug, not a to-do.", "",
             "## Rules", "", "| File | Owner step | Title |", "|---|---|---|"]
    for f, k, st, title in rows:
        if k == "rule":
            lines.append(f"| `{f}` | {st} | {title} |")
    lines += ["", "## Records (owner is the artifact or code they describe)", ""]
    for f in rec:
        lines.append(f"- `{f}`")
    lines += ["", "## Where to look for a rule", "",
              "| Question | Owner |", "|---|---|",
              "| Which chapter, what budget, what gate | `PIPELINE.md` |",
              "| Model provenance, revision pinning | `harness/1-model-qualification/RULES.md` |",
              "| Environment, metrics, concurrency grid, toolchain | `harness/2-preflight-conformance/RULES.md` |",
              "| How to search the parameter space | `harness/3-deployment-raster/RULES.md` |",
              "| Repetitions, confirmation grade | `harness/4-confirmation/RULES.md` |",
              "| Formal campaign, telemetry, artifacts | `harness/5-formal-campaign/RULES.md` |",
              "| Acceptance, comparators, publication | `harness/6-accept-and-publish/RULES.md` |",
              "| Charts, conclusion wording, pipeline feedback | `harness/7-report-and-feedback/RULES.md` |",
              "| What happened, including failures | `results/<host>/journal/` |", ""]
    # Written to stdout on demand. It used to be a tracked file, and a tracked generated
    # file that nothing verifies goes stale in silence: renaming a chapter title left the
    # index describing the old tree while every check still reported PASS.
    sys.stdout.write("\n".join(lines) + "\n")
    return 0


def main():
    args = sys.argv[1:]
    if "--emit-index" in args:
        return emit_index()
    viol = check()
    if "--update-baseline" in args:
        BASE.write_text(json.dumps({"pipeline_max_lines": PIPELINE_MAX_LINES,
                                    "violations": sorted(viol), "count": len(viol)}, indent=2) + "\n")
        print(f"baseline written: {len(viol)} known violations, PIPELINE.md cap {PIPELINE_MAX_LINES}")
        return 0
    known = set()
    if BASE.is_file():
        known = set(json.loads(BASE.read_text()).get("violations", []))
    fresh = [v for v in viol if v not in known] if "--full" not in args else viol
    for v in sorted(fresh):
        print(f"  VIOLATION {v}")
    if "--full" not in args:
        print(f"  ({len(viol) - len(fresh)} pre-existing violations baselined)")
        if len(fresh) < 10 and known:
            closed = known - set(viol)
            if closed:
                print(f"  note: {len(closed)} baselined violations now resolved - "
                      f"run --update-baseline to ratchet down")
    print(f"{'FAIL' if fresh else 'PASS'}: {len(fresh)} new violations "
          f"({len(viol)} total, {len(known)} baselined)")
    return 1 if fresh else 0


if __name__ == "__main__":
    sys.exit(main())
