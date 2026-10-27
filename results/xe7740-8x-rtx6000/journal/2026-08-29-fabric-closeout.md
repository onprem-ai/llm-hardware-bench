# Fabric qualification closeout — 2026-08-29

After the Qwen campaign completed 72/72 zero-error measured runs, its original
stale top-level manifest and marker were preserved and a hash-backed amendment
was generated from the authoritative run manifests. Only the three Qwen
containers were then stopped; all eight GPUs returned to zero allocated MiB.

Fabric result pointer:

```text
campaigns/fabric-qualification-20260829.yaml
```

Key findings:

- A matching pinned DCGM 4.6.0 utility image discovered the same 93 supported
  profiling fields on every GPU. The original exporter was restored afterward.
- DCGM PCIe RX and TX fields were emitted and changed on all eight GPU series
  under controlled TP4 all-reduce load.
- PCIe replay counters were emitted and remained unchanged at zero.
- All links negotiated PCIe Gen5 x16 under sustained eight-GPU load; idle Gen1
  observations are link power management, not down-training.
- CUDA P2P access was enabled for all GPU pairs. Enabled off-diagonal bandwidth
  ranged 34.18–42.47 GB/s unidirectional and 64.44–74.93 GB/s bidirectional.
- All 36 NCCL cases passed: four GPU groupings, three CPU/memory policies, and
  all-reduce/all-gather/reduce-scatter. The clean matrix contains 1,008 parsed
  rows and zero wrong values.
- Same-NUMA TP4 all-reduce reached 28.59–29.86 GB/s large-message median bus
  bandwidth when pinned locally. Equivalent cross-NUMA groups measured
  20.91–21.09 GB/s, a 26.9–29.4% penalty.
- Deliberately remote CPU/memory pinning reduced same-NUMA TP4 collective
  bandwidth by roughly 18.5–24.7%, depending on collective and group.
- Intel IMC read/write counters are available via `perf` and
  were captured through both idle and NCCL matrix windows.
- UPI PMU devices exist, but expose no named kernel events. A pinned Intel PCM
  container detected four UPI ports per socket but could not safely acquire the
  occupied/restricted PMUs. PCM `-r` was not used. UPI traffic is therefore
  explicitly unavailable, not zero.

The original `NCCL_DEBUG=INFO` matrix is retained for topology/algorithm
attribution. Because asynchronous debug text interleaved with some tabular
rows, a second `NCCL_DEBUG=WARN` matrix is authoritative for numeric parsing.
