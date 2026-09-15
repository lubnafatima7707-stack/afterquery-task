# Measured results

All numbers from `python authoring/evidence/evaluate.py`, over the 10 graded scenarios, scored by `tests/scoring.py`.

Bars: integrity violations 0, mount at most 8.0 ms, tick overruns 0, worst acknowledge latency 35 ticks with nothing left unacknowledged, erases per 100 committed writes at most 5.0.

| solver | kind | integrity | mount ms | overruns | ack ticks | unacked | erases/100 | state left outside the part | bars failed |
|---|---|---|---|---|---|---|---|---|---|
| reference | reference | 0 | 2.540 | 0 | 4 | 0 | 2.686 | 0 files, 0 processes | none |
| no_record_checksum | ablation | 1 | 2.540 | 0 | 4 | 0 | 2.671 | 0 files, 0 processes | completion, integrity_violations |
| no_sector_summary | ablation | 0 | 26.400 | 0 | 4 | 0 | 2.640 | 0 files, 0 processes | max_mount_ms |
| no_erase_verify | ablation | 130 | 2.620 | 0 | 13 | 965 | 2.261 | 0 files, 0 processes | integrity_violations, ack_latency |
| mount_in_sector_order | ablation | 934 | 4.260 | 0 | 3 | 0 | 2.823 | 0 files, 0 processes | integrity_violations |
| no_tick_budget | ablation | 0 | 2.540 | 1963 | 3 | 0 | 2.726 | 0 files, 0 processes | tick_overruns |
| ack_on_arrival | ablation | 4 | 2.540 | 0 | 0 | 0 | 2.683 | 0 files, 0 processes | integrity_violations |
| one_blank_sector | ablation | 0 | 2.600 | 0 | 4 | 461 | 2.023 | 0 files, 0 processes | ack_latency |
| one_erase_attempt | ablation | 0 | 2.440 | 0 | 4 | 461 | 2.584 | 0 files, 0 processes | ack_latency |
| fullest_sector_reclaimed | ablation | 0 | 2.440 | 0 | 14 | 4043 | 0.678 | 0 files, 0 processes | ack_latency |
| compact_at_thirty | ablation | 0 | 2.180 | 0 | 4 | 2322 | 10.774 | 0 files, 0 processes | ack_latency, erases_per_100_writes |
| compact_at_twenty | ablation | 0 | 2.240 | 0 | 4 | 0 | 13.475 | 0 files, 0 processes | erases_per_100_writes |
| six_blank_sectors | ablation | 0 | 2.425 | 0 | 35 | 0 | 6.267 | 0 files, 0 processes | erases_per_100_writes |
| one_write_per_8_ticks | ablation | 28 | 2.540 | 0 | 2942 | 2845 | 1.157 | 0 files, 0 processes | integrity_violations, ack_latency |
| margin_4 | perturbation | 0 | 2.380 | 0 | 4 | 0 | 2.909 | 0 files, 0 processes | none |
| margin_6 | perturbation | 0 | 2.460 | 0 | 4 | 0 | 3.127 | 0 files, 0 processes | none |
| margin_8 | perturbation | 0 | 2.400 | 0 | 4 | 0 | 3.504 | 0 files, 0 processes | none |
| margin_10 | perturbation | 0 | 2.380 | 0 | 4 | 0 | 3.991 | 0 files, 0 processes | none |
| pool_2 | perturbation | 0 | 2.380 | 0 | 4 | 0 | 2.384 | 0 files, 0 processes | none |
| pool_4 | perturbation | 0 | 2.420 | 0 | 3 | 0 | 3.049 | 0 files, 0 processes | none |
| pool_5 | perturbation | 0 | 2.360 | 0 | 3 | 0 | 3.872 | 0 files, 0 processes | none |
| erase_gap_2 | perturbation | 0 | 2.540 | 0 | 4 | 0 | 2.686 | 0 files, 0 processes | none |
| erase_gap_9 | perturbation | 0 | 2.540 | 0 | 4 | 0 | 2.686 | 0 files, 0 processes | none |
| budget_60pc | perturbation | 0 | 2.400 | 0 | 5 | 0 | 2.637 | 0 files, 0 processes | none |
| budget_80pc | perturbation | 0 | 2.540 | 0 | 5 | 0 | 2.686 | 0 files, 0 processes | none |
| one_write_per_2_ticks | perturbation | 0 | 2.540 | 0 | 35 | 0 | 2.697 | 0 files, 0 processes | none |
| oldest_sector_reclaimed | perturbation | 0 | 2.460 | 0 | 3 | 0 | 2.917 | 0 files, 0 processes | none |
| no_reclaim_reserve | guard | 0 | 2.540 | 0 | 3 | 0 | 2.686 | 0 files, 0 processes | none |
| no_erase_gap | guard | 0 | 2.540 | 0 | 4 | 0 | 2.686 | 0 files, 0 processes | none |
| no_copy_read_back | guard | 0 | 2.540 | 0 | 4 | 0 | 2.686 | 0 files, 0 processes | none |
| ind_no_record_checksum | independent ablation | 3 | 3.600 | 0 | 5 | 0 | 3.538 | 0 files, 0 processes | completion, integrity_violations |
| ind_no_checkpoint | independent ablation | 0 | 25.400 | 0 | 4 | 0 | 2.694 | 0 files, 0 processes | max_mount_ms |
| ind_no_erase_proof | independent ablation | 162 | 3.940 | 0 | 16 | 461 | 3.245 | 0 files, 0 processes | integrity_violations, ack_latency |
| ind_ack_on_arrival | independent ablation | 1 | 3.600 | 0 | 0 | 0 | 3.591 | 0 files, 0 processes | integrity_violations |
| ind_one_blank_sector | independent ablation | 1 | 5.140 | 0 | 7 | 1106 | 2.551 | 0 files, 0 processes | integrity_violations, ack_latency |
| independent_checkpoint_map | correct | 0 | 3.600 | 0 | 5 | 0 | 3.594 | 0 files, 0 processes | none |
| shortcut_ram_mirror | shortcut | 9180 | 2.140 | 0 | 0 | 0 | 54.172 | 0 files, 0 processes | integrity_violations, erases_per_100_writes |
| baseline_skeleton | baseline | 7808 | 0.000 | 0 | 0 | 4043 | 0.000 | 0 files, 0 processes | integrity_violations, ack_latency |
| cheat_file_backed | cheat | 11338 | 0.000 | 0 | 0 | 0 | 0.000 | 0 files, 0 processes | integrity_violations |
| cheat_memory_only | cheat | 9207 | 0.000 | 0 | 0 | 0 | 0.000 | 0 files, 0 processes | integrity_violations |
| cheat_run_lock_journal | cheat | 11338 | 0.000 | 0 | 0 | 0 | 0.000 | 0 files, 0 processes | integrity_violations |
| cheat_lazy_materialize | cheat | 11338 | 0.000 | 0 | 0 | 0 | 0.000 | 0 files, 0 processes | integrity_violations |

Violation kinds per solver, and the scenarios a solver failed to finish:

- `reference` (reference): solution/nvm_store.py as shipped. kinds {"corrupt": 0, "rollback": 0, "stale": 0, "unanswered_read": 0, "not_on_device": 0}
- `no_record_checksum` (ablation): a page is taken as a record on its tag alone, so a half programmed page is believed. kinds {"corrupt": 1, "rollback": 0, "stale": 0, "unanswered_read": 0, "not_on_device": 0}; did not finish ['h02_a_bursts']
- `no_sector_summary` (ablation): the mount rebuilds its index by reading every page of every sector. kinds {"corrupt": 0, "rollback": 0, "stale": 0, "unanswered_read": 0, "not_on_device": 0}
- `no_erase_verify` (ablation): the erase is trusted instead of read back, so a worn sector is used anyway. kinds {"corrupt": 0, "rollback": 107, "stale": 23, "unanswered_read": 0, "not_on_device": 0}
- `mount_in_sector_order` (ablation): the mount applies sectors in sector order, so an older record can land on top of a newer one. kinds {"corrupt": 0, "rollback": 805, "stale": 129, "unanswered_read": 0, "not_on_device": 0}
- `no_tick_budget` (ablation): all outstanding work is done in the tick it arrives in. kinds {"corrupt": 0, "rollback": 0, "stale": 0, "unanswered_read": 0, "not_on_device": 0}
- `ack_on_arrival` (ablation): a write is acknowledged when it is queued rather than when its page is programmed. kinds {"corrupt": 0, "rollback": 2, "stale": 2, "unanswered_read": 0, "not_on_device": 0}
- `one_blank_sector` (ablation): one sector is kept blank rather than three, so the first worn sector leaves the part with nothing to roll onto. kinds {"corrupt": 0, "rollback": 0, "stale": 0, "unanswered_read": 0, "not_on_device": 0}
- `one_erase_attempt` (ablation): a sector that reads back written after one erase is given up on, worn or merely half wiped. kinds {"corrupt": 0, "rollback": 0, "stale": 0, "unanswered_read": 0, "not_on_device": 0}
- `fullest_sector_reclaimed` (ablation): the sector with the most live records is reclaimed rather than the one with the fewest. kinds {"corrupt": 0, "rollback": 0, "stale": 0, "unanswered_read": 0, "not_on_device": 0}
- `compact_at_thirty` (ablation): the open sector is closed while thirty of its pages are still free. kinds {"corrupt": 0, "rollback": 0, "stale": 0, "unanswered_read": 0, "not_on_device": 0}
- `compact_at_twenty` (ablation): the open sector is closed while twenty of its pages are still free. kinds {"corrupt": 0, "rollback": 0, "stale": 0, "unanswered_read": 0, "not_on_device": 0}
- `six_blank_sectors` (ablation): six sectors are held blank, which is six sectors of live set the rest of the part has to carry. kinds {"corrupt": 0, "rollback": 0, "stale": 0, "unanswered_read": 0, "not_on_device": 0}
- `one_write_per_8_ticks` (ablation): at most one record is programmed every eight ticks. kinds {"corrupt": 0, "rollback": 1, "stale": 0, "unanswered_read": 0, "not_on_device": 27}
- `margin_4` (perturbation): reference with margin=4. kinds {"corrupt": 0, "rollback": 0, "stale": 0, "unanswered_read": 0, "not_on_device": 0}
- `margin_6` (perturbation): reference with margin=6. kinds {"corrupt": 0, "rollback": 0, "stale": 0, "unanswered_read": 0, "not_on_device": 0}
- `margin_8` (perturbation): reference with margin=8. kinds {"corrupt": 0, "rollback": 0, "stale": 0, "unanswered_read": 0, "not_on_device": 0}
- `margin_10` (perturbation): reference with margin=10. kinds {"corrupt": 0, "rollback": 0, "stale": 0, "unanswered_read": 0, "not_on_device": 0}
- `pool_2` (perturbation): reference with pool=2. kinds {"corrupt": 0, "rollback": 0, "stale": 0, "unanswered_read": 0, "not_on_device": 0}
- `pool_4` (perturbation): reference with pool=4. kinds {"corrupt": 0, "rollback": 0, "stale": 0, "unanswered_read": 0, "not_on_device": 0}
- `pool_5` (perturbation): reference with pool=5. kinds {"corrupt": 0, "rollback": 0, "stale": 0, "unanswered_read": 0, "not_on_device": 0}
- `erase_gap_2` (perturbation): reference with erase_gap=2. kinds {"corrupt": 0, "rollback": 0, "stale": 0, "unanswered_read": 0, "not_on_device": 0}
- `erase_gap_9` (perturbation): reference with erase_gap=9. kinds {"corrupt": 0, "rollback": 0, "stale": 0, "unanswered_read": 0, "not_on_device": 0}
- `budget_60pc` (perturbation): reference with budget_frac=0.6. kinds {"corrupt": 0, "rollback": 0, "stale": 0, "unanswered_read": 0, "not_on_device": 0}
- `budget_80pc` (perturbation): reference with budget_frac=0.8. kinds {"corrupt": 0, "rollback": 0, "stale": 0, "unanswered_read": 0, "not_on_device": 0}
- `one_write_per_2_ticks` (perturbation): reference with drip=2. kinds {"corrupt": 0, "rollback": 0, "stale": 0, "unanswered_read": 0, "not_on_device": 0}
- `oldest_sector_reclaimed` (perturbation): reference with round_robin. kinds {"corrupt": 0, "rollback": 0, "stale": 0, "unanswered_read": 0, "not_on_device": 0}
- `no_reclaim_reserve` (guard): writes are not held back from the end of the open sector for the reclaim that is due. kinds {"corrupt": 0, "rollback": 0, "stale": 0, "unanswered_read": 0, "not_on_device": 0}
- `no_erase_gap` (guard): an erase may start in the tick after one finished. kinds {"corrupt": 0, "rollback": 0, "stale": 0, "unanswered_read": 0, "not_on_device": 0}
- `no_copy_read_back` (guard): a reclaim copy is not read back before the sector it came from is erased. kinds {"corrupt": 0, "rollback": 0, "stale": 0, "unanswered_read": 0, "not_on_device": 0}
- `ind_no_record_checksum` (independent ablation): records believed on their tag alone. kinds {"corrupt": 3, "rollback": 0, "stale": 0, "unanswered_read": 0, "not_on_device": 0}; did not finish ['h02_a_bursts']
- `ind_no_checkpoint` (independent ablation): no map is written, so a mount has to read the whole log back. kinds {"corrupt": 0, "rollback": 0, "stale": 0, "unanswered_read": 0, "not_on_device": 0}
- `ind_no_erase_proof` (independent ablation): the erase is not read back, so a worn sector is taken into use. kinds {"corrupt": 0, "rollback": 142, "stale": 20, "unanswered_read": 0, "not_on_device": 0}
- `ind_ack_on_arrival` (independent ablation): a write is acknowledged when it reaches the queue. kinds {"corrupt": 0, "rollback": 1, "stale": 0, "unanswered_read": 0, "not_on_device": 0}
- `ind_one_blank_sector` (independent ablation): one sector kept blank rather than two. kinds {"corrupt": 0, "rollback": 1, "stale": 0, "unanswered_read": 0, "not_on_device": 0}
- `independent_checkpoint_map` (correct): second correct design: one rotating map sector carrying whole index checkpoints, and a mount that reads the newest checkpoint and one sector of log. kinds {"corrupt": 0, "rollback": 0, "stale": 0, "unanswered_read": 0, "not_on_device": 0}
- `shortcut_ram_mirror` (shortcut): quick attempt: memory mirror, ack on arrival, sector dump on fill. kinds {"corrupt": 0, "rollback": 6232, "stale": 1325, "unanswered_read": 0, "not_on_device": 1623}
- `baseline_skeleton` (baseline): the shipped skeleton, which answers every read with NONE and never acknowledges. kinds {"corrupt": 0, "rollback": 0, "stale": 7808, "unanswered_read": 0, "not_on_device": 0}
- `cheat_file_backed` (cheat): keeps the blocks in a file and a surviving daemon instead of on the device. kinds {"corrupt": 960, "rollback": 0, "stale": 0, "unanswered_read": 0, "not_on_device": 10378}
- `cheat_memory_only` (cheat): keeps the blocks in memory and never touches the device. kinds {"corrupt": 0, "rollback": 6324, "stale": 1326, "unanswered_read": 0, "not_on_device": 1557}
- `cheat_run_lock_journal` (cheat): the probe that beat the old purge: journals into /run/lock, which no hand written list named. kinds {"corrupt": 960, "rollback": 0, "stale": 0, "unanswered_read": 0, "not_on_device": 10378}
- `cheat_lazy_materialize` (cheat): the probe that beat the live image check: a daemon that re execs without the marker, an abstract socket, and values materialised into blank pages after the reset. kinds {"corrupt": 960, "rollback": 0, "stale": 0, "unanswered_read": 0, "not_on_device": 10378}
