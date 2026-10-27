# NUMA and uncore collection

- `probe-uncore.sh` inventories IMC/UPI PMUs and tests access without changing
  kernel policy.
- `sample-uncore-memory.sh` uses kernel-named Intel IMC events through
  passwordless `sudo perf stat` and preserves interval samples.

Counters that cannot be opened are unavailable, not zero. Do not invent UPI raw
event encodings when the kernel exposes UPI PMUs without named events.

Intel PCM may provide memory locality and UPI metrics, but it requires exclusive
PMU access and elevated device access. Do not use PCM `-r` to reset an occupied
PMU during observability or benchmark operation. Preserve the failure receipt
and report UPI unavailable if PCM cannot acquire the counters safely.
