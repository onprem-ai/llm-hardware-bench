# XE7740-04 Hardware-Capacity Study

This directory contains committed records specific to the hardware-capacity
study on `xe7740-04`. Generic methods and tools remain at repository root; raw
benchmark results remain external.

## Objective

Characterize practical LLM serving capacity across representative dense and MoE
models on the eight-GPU server, including throughput, latency, goodput, energy,
KV capacity, topology, PCIe/NCCL behavior, and operational limits.

## Contents

- [`study.yaml`](study.yaml): machine-readable study identity and references.
- [`concurrency-grids.yaml`](concurrency-grids.yaml): frozen
  model-specific global concurrency grids.
- [`hosts/xe7740-04.yaml`](hosts/xe7740-04.yaml): observed host/toolchain
  reference snapshot.
- [`campaigns/`](MODELS.md): small pointers to external campaign artifacts.
- [`journal/`](journal/): dated observations and decisions.
- [`todos/`](todos/): deferred actions with entry gates and acceptance criteria.

## Result policy

Do not copy raw campaign data here. Use the external result hierarchy defined in
`harness/5-formal-campaign/RULES.md` and commit only compact pointers and durable study
context.
