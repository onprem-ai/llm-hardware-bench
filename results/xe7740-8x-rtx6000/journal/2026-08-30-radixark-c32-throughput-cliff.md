# RadixArk full GLM-5.3 C32 decode throughput cliff

## Scope

Campaign:

```text
20260830-full-glm53-radixark-formal
```

Model and runtime:

```text
RadixArk/GLM-5.3-NVFP4
revision 363e8f086905afd83db356a620f9aa401c23800a
Infernal Invocation r18 / vLLM 0.26.1rc0+infernal.invocation.cu133.r18.vllmf0fa1ce.b12x75787c7
one TP8 replica
MTP-3
max_num_seqs=32
max_cudagraph_capture_size=64
```

This record documents an observed performance discontinuity and a likely
runtime mechanism. It does not claim that a corrective configuration has
already been qualified.

## Observation

Decode throughput rose normally through C16 and then fell sharply at C32. The
behavior repeated in all three repetitions.

| Concurrency | Median output tok/s | Observed range | Mean ITL, representative | Mean aggregate GPU board power |
|---:|---:|---:|---:|---:|
| C8 | 347.07 | 336.58-352.49 | 21-22 ms | approximately 1.87-1.88 kW |
| C16 | 413.96 | 410.19-414.67 | 33-34 ms | approximately 1.84-1.87 kW |
| C32 | 104.21 | 104.17-104.92 | 288-292 ms | approximately 1.27-1.28 kW |
| C64 | 102.87 | 101.11-103.16 | 300-305 ms | approximately 1.28-1.29 kW |
| C128 | 104.81 | 103.95-105.54 | 297-300 ms | approximately 1.28-1.30 kW |

C32 was not an isolated bad run: one repetition came from qualification and two
came from the formal campaign, yet all three converged near 104 output tok/s.
All runs completed without request errors.

At C16 the GPUs drew substantially more board power and showed much higher
memory-copy utilization than at C32 and above. GPU-utilization percentages
remained high, so the evidence points to a less efficient execution path rather
than a lack of offered work.

## Likely mechanism

The launch log records:

```text
num_speculative_tokens=3
max_num_seqs=32
max_cudagraph_capture_size=64
cudagraph_mode=FULL_AND_PIECEWISE
cudagraph_capture_sizes=[1,2,4,8,16,24,32,40,48,56,64]
```

A uniform MTP-3 verification step can require approximately:

```text
active requests * (1 target token + 3 speculative tokens)
```

Therefore:

```text
C16 * 4 = 64 tokens
C32 * 4 = 128 tokens
```

C16 fits the configured graph-capture ceiling exactly, while C32 does not. The
most likely explanation is that C32 crosses from an efficient captured path to
a slower eager or otherwise less-optimized speculative verification path.

This interpretation is consistent with upstream vLLM work documenting that
`max_cudagraph_capture_size` is expressed in tokens while speculative decode
widens a uniform decode batch by `1 + num_speculative_tokens`:

- vLLM PR #50488, "Capture the widest uniform decode batch by default":
  <https://github.com/vllm-project/vllm/pull/50488>
- Related concurrent MTP throughput-collapse report, vLLM issue #49548:
  <https://github.com/vllm-project/vllm/issues/49548>

The exact root cause is not yet proven for this custom r18 runtime. Confirmation
requires a controlled deployment change and repeated C16/C32 canaries.

## Can it be avoided?

Probably. The preferred mitigation is to capture the widest MTP verification
batch explicitly. For this deployment, the first candidate is:

```text
max_cudagraph_capture_size = max_num_seqs * (1 + MTP depth)
                           = 32 * 4
                           = 128
```

This is a hypothesis to qualify, not a validated production setting. Raising
the graph cap consumes additional GPU memory during graph capture and could
reduce KV-cache capacity or cause startup failure. It therefore requires a new
deployment identity and fresh readiness checks.

Other options, in descending order of preference:

1. Upgrade to a runtime containing a validated upstream fix for speculative
   decode capture sizing, after checking whether that fix is present and stable
   in the exact build.
2. Keep MTP-3 but explicitly capture size 128 if the runtime supports the
   required graph shape and memory remains sufficient.
3. Reduce MTP depth. The required width becomes
   `max_num_seqs * (1 + new_depth)`, but decode speed and acceptance economics
   must be requalified.
4. Limit admitted concurrency to C16. This avoids the observed cliff but leaves
   capacity unused and is a workaround, not a runtime fix.
5. Disable MTP or use eager execution only as diagnostic controls. Either change
   creates a different deployment and may reduce low-concurrency performance.

Increasing `max_num_seqs` alone is not a solution. It can increase memory use
and does not address the graph-width mismatch unless the graph-capture ceiling
also covers the speculative verification width.

## Minimal confirmation experiment

Create a new deployment differing only in graph capture size:

```text
existing: max_cudagraph_capture_size=64
candidate: max_cudagraph_capture_size=128
```

Required gates:

1. Load successfully at the same 0.95 GPU-memory utilization.
2. Confirm the startup log includes capture coverage through 128.
3. Confirm KV-token capacity remains acceptable.
4. Run decode C16 and C32, one canary repetition each.
5. If C32 recovers without instability, run three repetitions at C16 and C32.
6. Run balanced C16 and C32 to confirm the same boundary behavior.
7. Compare MTP acceptance, output TPS, TTFT, ITL, aggregate GPU board power,
   memory-copy utilization, and errors.

Acceptance criterion for the hypothesis: C32 no longer collapses near 104
output tok/s and instead remains near or above the C16 throughput region,
without OOM, request failures, or unacceptable KV-capacity loss.

Do not merge corrective canary measurements into the completed campaign. A
changed graph cap is a capacity-affecting deployment change and must have its
own deployment/campaign record.
