---
kind: rule
step: cross
title: Agent-facing pointer to PIPELINE.md
---

# Agent Instructions

## NON-NEGOTIABLE — no access or security details anywhere in this repository

This repository is meant to be published. Nothing in it — not code, scripts, configs,
results, journals, logs, or commit messages — may reveal how to reach or get into a
machine. This overrides every other instruction, deadline, and convenience. No exceptions,
not "temporarily", not "just a default value", not in a throwaway script.

Never commit:

- IP addresses (except loopback / `0.0.0.0` bind addresses), real hostnames or
  domain names of our machines, `user@host` targets, ports exposed to the network;
- credentials of any kind: passwords, API keys, tokens, private keys, certificates,
  SSH config or `known_hosts` entries;
- privilege or access configuration: passwordless / `NOPASSWD` sudo, root login,
  which accounts exist or can log in, firewall rules;
- VPN, tunnel, overlay-network, SSH, BMC/IPMI/iDRAC product names, setup, or topology.

Scripts that need a target host take it from the environment **with no default**:
`NODE=${NODE:?set NODE=<user>@<host>}`. Results record a capability by its effect
("IMC counters captured via perf"), never by the privilege that made it possible.

If you find such a detail already in the repo, stop and tell the user: remove it, and
flag that it also lives in git history and needs a history rewrite. Do not work around
`harness/check_repo.py` rule 10 — fix the content.

## Read this first — before any benchmark work

**`PIPELINE.md` is the single authority on how to proceed**: the seven chapters, which
sub-steps are mechanical vs agentic, wall-clock budgets, critical-path scheduling, entry
and exit gates, the naming contract, and pipeline rules R-PIPE-1..7.

Do not reconstruct procedure from memory or from a journal — the
latter is a legacy reference being dissolved chapter by chapter and disagrees with
`PIPELINE.md` in places. Where two documents state the same rule, only one owns it; check
`harness/MOVED.md` for the mapping.

Before stating any number, register the comparator:

```
python3 harness/6-accept-and-publish/code/validate_claims.py <campaign>/6-acceptance/claims.yaml
```

A delta that does not resolve to `results/<host>/comparators.json` does not get written down. This rule
exists because an unverified remembered comparator (1111 tok/s, which never existed)
consumed three designed experiments and roughly an hour of eight-GPU time on 2026-09-06.

# Agent Instructions

## Version control

This is a fast-moving prototyping repository. Commit directly to `main` and push;
do not create feature branches, and do not wait for review before committing.
Commit a coherent unit of work with its evidence, then push. Only branch when an
experiment must be abandoned without polluting `main`.

**Every commit must carry this co-author trailer** (as the last line of the message,
after a blank line), no exceptions:

```
Co-authored-by: Anathapindika <6978736+Anathapindika@users.noreply.github.com>
```

## Model downloads

The full acquisition procedure is owned by chapter 1: [`harness/1-model-qualification/RULES.md`](harness/1-model-qualification/RULES.md) (rules R-01-1..R-01-13). Read it before downloading anything; it is not summarised here so that this file cannot drift from it.

Two of its rules are listed here only because violating them is unrecoverable: resolve the revision to a commit **before** transferring payload (R-01-1), and never invent an upstream revision or hash to close a provenance gap (R-01-10).

## Journal scope — LLM and benchmark content only

Journals, campaign notes, and publication records describe the LLM, the serving
stack, and the benchmark. Nothing else. Access infrastructure is off-topic and
must never appear in them, because it is the class of content most likely to
leak sensitive operational information:

- no IP addresses (loopback bind addresses in deployment configs are fine),
- no VPN, tunnel, overlay-network, SSH, host-key, or BMC/IPMI product names or
  configuration,
- no credentials, hostnames-of-record, or network topology.

A host or network event is recordable **only by its effect on the measurement**
— "the host's network path was lost for ~3 h; nothing detected it
automatically; 55 runs completed inside the blind window" — never by its
configuration or access details. `harness/check_repo.py` rule 10 refuses any
study file that carries these details; a fix means rewriting the passage to the
measurement effect, not silencing the check.
