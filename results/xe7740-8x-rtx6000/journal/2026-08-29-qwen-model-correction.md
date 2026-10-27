# Qwen model identity correction — 2026-08-29

The completed 72-run campaign was originally stored below a misleading
`qwen38-flash` directory and used this exact checkpoint:

```text
unsloth/Qwen3.8-27B-NVFP4
revision 16b6615af3548b88e2d8e382457bc705b00479cf
```

That checkpoint is a 27B model and must not be described as the intended
Qwen3.8 Flash model. The directory name was misleading; the run manifests and
campaign pointer preserve the actual model identity.

At explicit operator request, the downloaded checkpoint payload was deleted
after confirming that no process or running container referenced it. Benchmark
results were not deleted.

The model study directory was subsequently renamed to
`qwen38-27b-nvfp4`. Raw benchmark files were not rewritten, so their embedded
historical absolute paths may still contain `qwen38-flash`; the relocation
receipt documents this explicitly.

Deletion receipt:

```text
/home/demouser/benchmarks/results/xe7740-8x-rtx6000/qwen38-27b-nvfp4/QWEN38-27B-WEIGHTS-DELETION-20260829.txt
```

Directory relocation receipt:

```text
/home/demouser/benchmarks/results/xe7740-8x-rtx6000/qwen38-27b-nvfp4/DIRECTORY-RENAME-20260829.txt
```

Deleted path:

```text
/home/demouser/models/unsloth--Qwen3.8-27B-NVFP4--model
```

Recorded size before deletion: 23,444,504,817 bytes across 13 files.

Any future Qwen3.8 Flash campaign must use a separately identified, pinned, and
verified Flash checkpoint and a non-ambiguous study/campaign slug.
