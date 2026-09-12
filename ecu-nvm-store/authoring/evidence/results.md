# Measured results

All numbers from `python authoring/evidence/evaluate.py`, over the 10 graded scenarios, scored by `tests/scoring.py`.

Bars: integrity violations 0, mount at most 8.0 ms, tick overruns 0, worst acknowledge latency 35 ticks with nothing left unacknowledged, erases per 100 committed writes at most 6.0.

| solver | kind | integrity | mount ms | overruns | ack ticks | unacked | erases/100 | bars failed |
|---|---|---|---|---|---|---|---|---|
| reference | reference | 0 | 2.880 | 0 | 11 | 0 | 2.491 | none |
| no_record_checksum | ablation | 1 | 2.880 | 0 | 11 | 0 | 2.455 | completion, integrity_violations |
| no_seal | ablation | 429 | 2.840 | 0 | 11 | 0 | 2.130 | integrity_violations |
| no_erase_verify | ablation | 31 | 2.880 | 0 | 9 | 0 | 2.448 | integrity_violations |
| no_tick_budget | ablation | 0 | 2.880 | 222 | 6 | 0 | 2.497 | tick_overruns |
| mount_full_scan | ablation | 0 | 28.475 | 0 | 11 | 0 | 2.491 | max_mount_ms |
| ack_on_arrival | ablation | 49 | 2.880 | 0 | 0 | 0 | 2.475 | integrity_violations |
| compact_too_early | ablation | 0 | 2.300 | 0 | 13 | 0 | 9.558 | erases_per_100_writes |
| one_write_per_8_ticks | ablation | 0 | 2.880 | 0 | 764 | 423 | 2.790 | ack_latency |
| one_write_per_2_ticks | ablation | 0 | 2.880 | 0 | 54 | 0 | 2.487 | ack_latency |
| deferred_full_scan | ablation | 1161 | 0.000 | 2 | 17 | 0 | 2.491 | integrity_violations, tick_overruns |
| margin_2 | perturbation | 0 | 2.860 | 0 | 13 | 0 | 2.582 | none |
| margin_4 | perturbation | 0 | 2.820 | 0 | 13 | 0 | 2.711 | none |
| margin_10 | perturbation | 0 | 2.700 | 0 | 13 | 0 | 3.207 | none |
| budget_60pc | perturbation | 0 | 2.880 | 0 | 17 | 0 | 2.493 | none |
| budget_80pc | perturbation | 0 | 2.880 | 0 | 13 | 0 | 2.491 | none |
| ind_no_record_checksum | independent ablation | 3 | 2.900 | 0 | 12 | 0 | 1.978 | completion, integrity_violations |
| ind_no_snapshot_refresh | independent ablation | 0 | 2.900 | 0 | 11 | 0 | 1.894 | none |
| ind_no_erase_proof | independent ablation | 2 | 2.900 | 0 | 8 | 0 | 1.853 | integrity_violations |
| ind_no_head_fallback | independent ablation | 118 | 2.900 | 0 | 12 | 0 | 1.853 | integrity_violations |
| ind_ack_on_arrival | independent ablation | 6 | 2.900 | 0 | 12 | 0 | 1.889 | integrity_violations |
| independent_circular_log | correct | 0 | 2.900 | 0 | 12 | 0 | 1.894 | none |
| shortcut_ram_mirror | shortcut | 1096 | 2.860 | 0 | 0 | 0 | 2.403 | integrity_violations |
| baseline_skeleton | baseline | 2854 | 0.000 | 0 | 0 | 1113 | 0.000 | integrity_violations, ack_latency |

Violation kinds per solver, and the scenarios a solver failed to finish:

- `reference` (reference): solution/nvm_store.py as shipped. kinds {"corrupt": 0, "rollback": 0, "stale": 0, "unanswered_read": 0}
- `no_record_checksum` (ablation): a page is taken as a record on its tag alone, so a half programmed page is believed. kinds {"corrupt": 1, "rollback": 0, "stale": 0, "unanswered_read": 0}; did not finish ['h02_a_bursts']
- `no_seal` (ablation): the sector with the highest generation wins even when its copy never finished. kinds {"corrupt": 0, "rollback": 429, "stale": 0, "unanswered_read": 0}
- `no_erase_verify` (ablation): the erase is trusted instead of read back, so a worn sector is used anyway. kinds {"corrupt": 0, "rollback": 28, "stale": 2, "unanswered_read": 1}
- `no_tick_budget` (ablation): all outstanding work is done in the tick it arrives in. kinds {"corrupt": 0, "rollback": 0, "stale": 0, "unanswered_read": 0}
- `mount_full_scan` (ablation): the mount rebuilds its index from every page of every sector. kinds {"corrupt": 0, "rollback": 0, "stale": 0, "unanswered_read": 0}
- `ack_on_arrival` (ablation): a write is acknowledged when it is queued rather than when its page is programmed. kinds {"corrupt": 0, "rollback": 49, "stale": 0, "unanswered_read": 0}
- `compact_too_early` (ablation): compaction starts while thirty pages of the active sector are still free. kinds {"corrupt": 0, "rollback": 0, "stale": 0, "unanswered_read": 0}
- `one_write_per_8_ticks` (ablation): at most one record is programmed every eight ticks. kinds {"corrupt": 0, "rollback": 0, "stale": 0, "unanswered_read": 0}
- `one_write_per_2_ticks` (ablation): at most one record is programmed every other tick. kinds {"corrupt": 0, "rollback": 0, "stale": 0, "unanswered_read": 0}
- `deferred_full_scan` (ablation): nothing is spent at MOUNT and the whole part is scanned from inside the ticks instead, reads answered BUSY until it is done. kinds {"corrupt": 0, "rollback": 3, "stale": 122, "unanswered_read": 1036}
- `margin_2` (perturbation): reference with margin=2. kinds {"corrupt": 0, "rollback": 0, "stale": 0, "unanswered_read": 0}
- `margin_4` (perturbation): reference with margin=4. kinds {"corrupt": 0, "rollback": 0, "stale": 0, "unanswered_read": 0}
- `margin_10` (perturbation): reference with margin=10. kinds {"corrupt": 0, "rollback": 0, "stale": 0, "unanswered_read": 0}
- `budget_60pc` (perturbation): reference with budget_frac=0.6. kinds {"corrupt": 0, "rollback": 0, "stale": 0, "unanswered_read": 0}
- `budget_80pc` (perturbation): reference with budget_frac=0.8. kinds {"corrupt": 0, "rollback": 0, "stale": 0, "unanswered_read": 0}
- `ind_no_record_checksum` (independent ablation): records believed on their tag alone. kinds {"corrupt": 3, "rollback": 0, "stale": 0, "unanswered_read": 0}; did not finish ['h02_a_bursts', 'h05_b_resets']
- `ind_no_snapshot_refresh` (independent ablation): the victim is erased without a fresh index snapshot, so a stored snapshot can name a reclaimed page. kinds {"corrupt": 0, "rollback": 0, "stale": 0, "unanswered_read": 0}
- `ind_no_erase_proof` (independent ablation): the erase is not read back, so a worn sector is taken into use. kinds {"corrupt": 0, "rollback": 2, "stale": 0, "unanswered_read": 0}
- `ind_no_head_fallback` (independent ablation): the newest generation is taken as the head even when its snapshot never landed. kinds {"corrupt": 0, "rollback": 118, "stale": 0, "unanswered_read": 0}
- `ind_ack_on_arrival` (independent ablation): a write is acknowledged when it reaches the queue. kinds {"corrupt": 0, "rollback": 6, "stale": 0, "unanswered_read": 0}
- `independent_circular_log` (correct): second correct design: circular log, index snapshots, oldest sector reclaimed. kinds {"corrupt": 0, "rollback": 0, "stale": 0, "unanswered_read": 0}
- `shortcut_ram_mirror` (shortcut): quick attempt: memory mirror, ack on arrival, sector dump on fill. kinds {"corrupt": 0, "rollback": 1096, "stale": 0, "unanswered_read": 0}
- `baseline_skeleton` (baseline): the shipped skeleton, which answers every read with NONE and never acknowledges. kinds {"corrupt": 0, "rollback": 0, "stale": 2854, "unanswered_read": 0}
