# 2026-09-25 — comino-8xrtx6000 hardware inventory

Full inventory collected 2026-09-25 (32 raw files under
`assets/hardware-inventory-20260925/`, structured record
`hosts/comino-8x.yaml`). Measurement-relevant findings:

- Board: ASRockRack TURIND8X-2T/500W, AMI BIOS 5.35 (2026-02-13).
- CPU: single AMD EPYC 9575F, 64C/128T, 1 socket, 1 NUMA node, 1500-5008 MHz,
  256 MiB L3. Single-socket means TP8 deployments share one host domain; NUMA
  pinning is moot (and was not pinned in either campaign).
- Memory: 768 GB = 8 x 96 GB DDR5-5600, 8 of 12 channels populated — host RAM
  bandwidth is channel-limited relative to a fully populated platform.
- GPUs: 8 x RTX PRO 6000 Blackwell Server Edition (VBIOS 98.02.AF.00.01,
  600 W cap, SM 12.0, PCIe Gen5 x16). No NVLink: every GPU pair is NODE via the
  root complex, so TP2 replica boundaries are also PCIe boundaries (the qwen
  4x TP2 recipe never crosses a GPU-GPU fabric link).
- GPU3 negotiated x8 (x16 capable) — a link-width anomaly on one accelerator.
  All measured campaigns predate noticing it; no campaign placed extra H2D
  traffic on GPU3 by design, but any future PCIe-bound workload comparison
  should re-check link width per GPU before attributing deltas to silicon.
- Storage: single Phison E16 PCIe Gen4 1 TB NVMe on the root — the cold-boot
  bound for the 433 GiB GLM load. Model payloads load in ~38 s only when the
  host page cache is warm (673 of 755 GB cached after first load).
- OS/driver: Ubuntu 24.04.5, kernel 6.8.0-139, NVIDIA driver 595.91.07, Docker
  29.8.1, secure boot off, IOMMU off, schedutil governor.

The inventory files were swept for access-adjacent content (rule 10): only
loopback netmasks appear (docker network inspect); no addresses, credentials,
or management interfaces are recorded.
