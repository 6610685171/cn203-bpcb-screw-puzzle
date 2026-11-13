# Final benchmark summary

Generated: 2026-11-13T13:34:48.203534+00:00

| Split | Method | n | Nodes | Node reduction | Sum of median times | Speedup | Bound prunes | Fallbacks |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| development | baseline | 60 | 59,018 | 0.00% | 22594.28 ms | 1.000x | 0 | 0 |
| development | bpcb1 | 60 | 45,691 | 22.58% | 20632.54 ms | 1.095x | 8,196 | 0 |
| development | bpcb2 | 60 | 22,462 | 61.94% | 10836.51 ms | 2.085x | 7,889 | 0 |
| development | bpcb12 | 60 | 20,114 | 65.92% | 10997.65 ms | 2.054x | 8,374 | 0 |
| holdout | baseline | 40 | 44,549 | 0.00% | 17768.65 ms | 1.000x | 0 | 0 |
| holdout | bpcb1 | 40 | 27,812 | 37.57% | 13449.76 ms | 1.321x | 7,898 | 0 |
| holdout | bpcb2 | 40 | 21,684 | 51.33% | 11629.61 ms | 1.528x | 4,967 | 0 |
| holdout | bpcb12 | 40 | 15,972 | 64.15% | 9580.23 ms | 1.855x | 4,941 | 0 |

Correctness condition: every measured status matched its frozen exact label, and every returned solution passed replay validation.

Timing is the per-instance median of repeated wall-clock measurements after warm-up. Node counts are the primary machine-independent metric.
