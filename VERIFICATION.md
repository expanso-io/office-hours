# Verification — September 7, 2026 (Pacific)

Executed on macOS with Expanso Edge v2.1.21.

| Check | Observed result |
| --- | --- |
| Feed unit tests | 3 passed |
| Ruff lint and formatting | Passed |
| Edge validation | All 3 pipeline configurations passed |
| CSV local execution | 2 warning JSON records, 8 Parquet files, 1 dead-letter record |
| Gzip local execution | 10 output records, sequence IDs 0–9 exactly once |
| Multiline local execution | 10 events, each with 5 lines and its nested cause |
| Benchmark passthrough | Both 1,000/s and 5,000/s rungs passed; 0 reported drops |
| Benchmark JSON transform | Both 1,000/s and 5,000/s rungs passed; 0 reported drops |

Benchmark source: `expanso-io/benchmarking` commit
`40bf64623e3d1aff3ad33671d8ea5d38ae698d71`. Host: Apple M5 Max, 18 cores,
64 GB RAM. Metrics dataset, TCP input, TCP sink, batch 1,000, 3-second rungs.
These are short operation checks, not performance comparisons or capacity claims.
Other local rehearsal work overlapped part of the benchmark window.
Filter throughput is calibrated for intentional record removal; its reported
processed rate is input-equivalent, not the raw receiver count.

The pipeline rehearsals create separate local Edge processes and inspect actual
written output. Each process is stopped in cleanup. No Cloud job or public
presenter UI was deployed for these checks. Generated logs and raw result files
are ignored under `.runtime/` to avoid publishing machine-specific paths.

## Remaining boundaries

- Session 001 is reconstructed, not the original exported live YAML/simulator.
- Session 002 needs presenter/OBS rehearsal before being called broadcast-ready.
- Cloud execution, if desired for session 002, needs a separate rehearsal.
- Gzip is a compressed structured feed, not a general proprietary binary decoder.
- Parquet files were checked for count and valid envelope markers, not decoded
  by an independent reader in the rehearsal.
