# Measured results

All numbers from `python authoring/evidence/evaluate.py`, over the 10 graded scenarios, scored by `tests/scoring.py`.

Bars: integrity violations 0, mount at most 8.0 ms, tick overruns 0, worst acknowledge latency 35 ticks with nothing left unacknowledged, erases per 100 committed writes at most 5.0.

| solver | kind | integrity | mount ms | overruns | ack ticks | unacked | erases/100 | state left outside the part | bars failed |
|---|---|---|---|---|---|---|---|---|---|
| reference | reference | 0 | 2.380 | 0 | 4 | 0 | 2.384 | 0 files, 0 processes | none |
| no_record_checksum | ablation | 3 | 2.375 | 0 | 4 | 0 | 2.375 | 0 files, 0 processes | completion, integrity_violations |
| no_sector_summary | ablation | 0 | 27.875 | 0 | 4 | 0 | 2.379 | 0 files, 0 processes | max_mount_ms |
| no_erase_verify | ablation | 99 | 2.680 | 0 | 12 | 965 | 1.932 | 0 files, 0 processes | integrity_violations, ack_latency |
| mount_in_sector_order | ablation | 1000 | 4.260 | 0 | 4 | 0 | 2.457 | 0 files, 0 processes | integrity_violations |
| no_tick_budget | ablation | 0 | 2.450 | 1763 | 4 | 0 | 2.408 | 6 files, 0 processes | tick_overruns |
| ack_on_arrival | ablation | 6 | 2.380 | 0 | 0 | 0 | 2.382 | 4 files, 0 processes | integrity_violations |
| one_blank_sector | ablation | 0 | 2.600 | 0 | 4 | 461 | 2.023 | 40 files, 0 processes | ack_latency |
| one_erase_attempt | ablation | 0 | 2.375 | 0 | 4 | 461 | 2.288 | 56 files, 0 processes | ack_latency |
| fullest_sector_reclaimed | ablation | 1 | 2.440 | 0 | 17 | 4043 | 0.468 | 29 files, 0 processes | integrity_violations, ack_latency |
| compact_at_thirty | ablation | 0 | 2.180 | 0 | 4 | 2322 | 9.194 | 0 files, 0 processes | ack_latency, erases_per_100_writes |
| compact_at_twenty | ablation | 0 | 2.280 | 0 | 4 | 461 | 8.082 | 0 files, 0 processes | ack_latency, erases_per_100_writes |
| six_blank_sectors | ablation | 0 | 2.425 | 0 | 35 | 0 | 6.267 | 0 files, 0 processes | erases_per_100_writes |
| one_write_per_8_ticks | ablation | 39 | 2.380 | 0 | 2942 | 2858 | 1.010 | 0 files, 0 processes | integrity_violations, ack_latency |
| compact_at_ten | ablation | 0 | 2.360 | 0 | 4 | 461 | 3.204 | 0 files, 0 processes | ack_latency |
| margin_4 | perturbation | 0 | 2.420 | 0 | 4 | 0 | 2.597 | 0 files, 0 processes | none |
| pool_3 | perturbation | 0 | 2.540 | 0 | 4 | 0 | 2.686 | 0 files, 0 processes | none |
| pool_5 | perturbation | 0 | 2.360 | 0 | 3 | 0 | 3.872 | 0 files, 0 processes | none |
| erase_gap_2 | perturbation | 0 | 2.380 | 0 | 4 | 0 | 2.384 | 0 files, 0 processes | none |
| erase_gap_9 | perturbation | 0 | 2.475 | 0 | 4 | 0 | 2.392 | 0 files, 0 processes | none |
| budget_60pc | perturbation | 0 | 2.440 | 0 | 7 | 0 | 2.384 | 0 files, 0 processes | none |
| budget_80pc | perturbation | 0 | 2.475 | 0 | 5 | 0 | 2.392 | 0 files, 0 processes | none |
| one_write_per_2_ticks | perturbation | 0 | 2.520 | 0 | 35 | 0 | 2.404 | 0 files, 0 processes | none |
| oldest_sector_reclaimed | perturbation | 0 | 2.520 | 0 | 3 | 0 | 2.562 | 0 files, 0 processes | none |
| no_reclaim_reserve | guard | 0 | 2.380 | 0 | 3 | 0 | 2.384 | 0 files, 0 processes | none |
| no_erase_gap | guard | 0 | 2.380 | 0 | 4 | 0 | 2.384 | 0 files, 0 processes | none |
| no_copy_read_back | guard | 0 | 2.380 | 0 | 4 | 0 | 2.384 | 0 files, 0 processes | none |
| ind_no_record_checksum | independent ablation | 3 | 3.960 | 0 | 7 | 0 | 3.050 | 0 files, 0 processes | completion, integrity_violations |
| ind_no_checkpoint | independent ablation | 0 | 26.625 | 0 | 4 | 0 | 2.379 | 0 files, 0 processes | max_mount_ms |
| ind_no_erase_proof | independent ablation | 70 | 3.740 | 0 | 14 | 504 | 2.715 | 0 files, 0 processes | integrity_violations, ack_latency |
| ind_ack_on_arrival | independent ablation | 4 | 4.020 | 0 | 0 | 0 | 3.108 | 0 files, 0 processes | integrity_violations |
| ind_one_blank_sector | independent ablation | 1 | 5.140 | 0 | 7 | 1106 | 2.551 | 0 files, 0 processes | integrity_violations, ack_latency |
| independent_checkpoint_map | correct | 0 | 4.020 | 0 | 7 | 0 | 3.110 | 0 files, 0 processes | none |
| shortcut_ram_mirror | shortcut | 9180 | 2.140 | 0 | 0 | 0 | 54.172 | 0 files, 0 processes | integrity_violations, erases_per_100_writes |
| baseline_skeleton | baseline | 7808 | 0.000 | 0 | 0 | 4043 | 0.000 | 0 files, 0 processes | integrity_violations, ack_latency |
| cheat_file_backed | cheat | 11338 | 0.000 | 0 | 0 | 0 | 0.000 | 0 files, 0 processes | integrity_violations |
| cheat_memory_only | cheat | 9207 | 0.000 | 0 | 0 | 0 | 0.000 | 0 files, 0 processes | integrity_violations |
| cheat_run_lock_journal | cheat | 11338 | 0.000 | 0 | 0 | 0 | 0.000 | 0 files, 0 processes | integrity_violations |
| cheat_lazy_materialize | cheat | 11338 | 0.000 | 0 | 0 | 0 | 0.000 | 0 files, 0 processes | integrity_violations |

Violation kinds per solver, and the scenarios a solver failed to finish:

- `reference` (reference): solution/nvm_store.py as shipped. kinds {"corrupt": 0, "rollback": 0, "stale": 0, "unanswered_read": 0, "not_on_device": 0}
- `no_record_checksum` (ablation): a page is taken as a record on its tag alone, so a half programmed page is believed. kinds {"corrupt": 3, "rollback": 0, "stale": 0, "unanswered_read": 0, "not_on_device": 0}; did not finish ['h02_a_bursts']
- `no_sector_summary` (ablation): the mount rebuilds its index by reading every page of every sector. kinds {"corrupt": 0, "rollback": 0, "stale": 0, "unanswered_read": 0, "not_on_device": 0}
- `no_erase_verify` (ablation): the erase is trusted instead of read back, so a worn sector is used anyway. kinds {"corrupt": 0, "rollback": 82, "stale": 17, "unanswered_read": 0, "not_on_device": 0}
- `mount_in_sector_order` (ablation): the mount applies sectors in sector order, so an older record can land on top of a newer one. kinds {"corrupt": 0, "rollback": 870, "stale": 130, "unanswered_read": 0, "not_on_device": 0}
- `no_tick_budget` (ablation): all outstanding work is done in the tick it arrives in. kinds {"corrupt": 0, "rollback": 0, "stale": 0, "unanswered_read": 0, "not_on_device": 0}
- `ack_on_arrival` (ablation): a write is acknowledged when it is queued rather than when its page is programmed. kinds {"corrupt": 0, "rollback": 3, "stale": 3, "unanswered_read": 0, "not_on_device": 0}
- `one_blank_sector` (ablation): one sector is kept blank rather than two, so a reclaim that finds a worn sector has nowhere to go. kinds {"corrupt": 0, "rollback": 0, "stale": 0, "unanswered_read": 0, "not_on_device": 0}
- `one_erase_attempt` (ablation): a sector that reads back written after one erase is given up on, worn or merely half wiped. kinds {"corrupt": 0, "rollback": 0, "stale": 0, "unanswered_read": 0, "not_on_device": 0}
- `fullest_sector_reclaimed` (ablation): the sector with the most live records is reclaimed rather than the one with the fewest. kinds {"corrupt": 0, "rollback": 1, "stale": 0, "unanswered_read": 0, "not_on_device": 0}
- `compact_at_thirty` (ablation): the open sector is closed while thirty of its pages are still free. kinds {"corrupt": 0, "rollback": 0, "stale": 0, "unanswered_read": 0, "not_on_device": 0}
- `compact_at_twenty` (ablation): the open sector is closed while twenty of its pages are still free. kinds {"corrupt": 0, "rollback": 0, "stale": 0, "unanswered_read": 0, "not_on_device": 0}
- `six_blank_sectors` (ablation): six sectors are held blank, which is six sectors of live set the rest of the part has to carry. kinds {"corrupt": 0, "rollback": 0, "stale": 0, "unanswered_read": 0, "not_on_device": 0}
- `one_write_per_8_ticks` (ablation): at most one record is programmed every eight ticks. kinds {"corrupt": 0, "rollback": 1, "stale": 0, "unanswered_read": 0, "not_on_device": 38}
- `compact_at_ten` (ablation): the open sector is closed while ten of its pages are still free. kinds {"corrupt": 0, "rollback": 0, "stale": 0, "unanswered_read": 0, "not_on_device": 0}
- `margin_4` (perturbation): reference with margin=4. kinds {"corrupt": 0, "rollback": 0, "stale": 0, "unanswered_read": 0, "not_on_device": 0}
- `pool_3` (perturbation): reference with pool=3. kinds {"corrupt": 0, "rollback": 0, "stale": 0, "unanswered_read": 0, "not_on_device": 0}
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
- `ind_no_erase_proof` (independent ablation): the erase is not read back, so a worn sector is taken into use. kinds {"corrupt": 0, "rollback": 58, "stale": 12, "unanswered_read": 0, "not_on_device": 0}
- `ind_ack_on_arrival` (independent ablation): a write is acknowledged when it reaches the queue. kinds {"corrupt": 0, "rollback": 1, "stale": 1, "unanswered_read": 0, "not_on_device": 2}
- `ind_one_blank_sector` (independent ablation): one sector kept blank rather than two. kinds {"corrupt": 0, "rollback": 1, "stale": 0, "unanswered_read": 0, "not_on_device": 0}
- `independent_checkpoint_map` (correct): second correct design: one rotating map sector carrying whole index checkpoints, and a mount that reads the newest checkpoint and one sector of log. kinds {"corrupt": 0, "rollback": 0, "stale": 0, "unanswered_read": 0, "not_on_device": 0}
- `shortcut_ram_mirror` (shortcut): quick attempt: memory mirror, ack on arrival, sector dump on fill. kinds {"corrupt": 0, "rollback": 6232, "stale": 1325, "unanswered_read": 0, "not_on_device": 1623}
- `baseline_skeleton` (baseline): the shipped skeleton, which answers every read with NONE and never acknowledges. kinds {"corrupt": 0, "rollback": 0, "stale": 7808, "unanswered_read": 0, "not_on_device": 0}
- `cheat_file_backed` (cheat): keeps the blocks in a file and a surviving daemon instead of on the device. kinds {"corrupt": 960, "rollback": 0, "stale": 0, "unanswered_read": 0, "not_on_device": 10378}
- `cheat_memory_only` (cheat): keeps the blocks in memory and never touches the device. kinds {"corrupt": 0, "rollback": 6324, "stale": 1326, "unanswered_read": 0, "not_on_device": 1557}
- `cheat_run_lock_journal` (cheat): the probe that beat the old purge: journals into /run/lock, which no hand written list named. kinds {"corrupt": 960, "rollback": 0, "stale": 0, "unanswered_read": 0, "not_on_device": 10378}
- `cheat_lazy_materialize` (cheat): the probe that beat the live image check: a daemon that re execs without the marker, an abstract socket, and values materialised into blank pages after the reset. kinds {"corrupt": 960, "rollback": 0, "stale": 0, "unanswered_read": 0, "not_on_device": 10378}
