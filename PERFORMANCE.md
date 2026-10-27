# Performance history

The authenticated Minecraft Admin dashboard records numeric performance samples in `~/minecraft-bedrock/admin-state/performance.sqlite`. The SQLite file is outside the Cockpit package and public website. No player names, positions, inventories, raw logs, or credentials are stored in this history.

## Collected values

- Docker CPU usage, in percent of one logical CPU. A multi-core workload may exceed 100%.
- Docker-reported memory usage and limit, normalized to MiB.
- Estimated TPS from the latest fresh in-game bridge reading.
- Number of online players from that same fresh reading.
- Server state and a fixed reason code if collection is partial or unavailable.

The collector rejects stale readings and snapshots from before the current server start. Missing TPS and unavailable player counts remain null, not zero. A stopped server has zero connected players and no TPS measurement. Failed collections record only a fixed status code; exception payloads are not saved.

## Scheduling

Install `history.py` next to `admin.py`. The collector uses the same Linux account and existing Docker permissions as the Cockpit panel. Create a first sample:

```sh
python3 "$HOME/minecraft-bedrock/admin/history.py"
```

Add this line to that account's crontab while preserving existing jobs:

```cron
* * * * * umask 077; /usr/bin/flock -n "$HOME/minecraft-bedrock/admin-state/history-collector.lock" /usr/bin/python3 "$HOME/minecraft-bedrock/admin/history.py" --collect-minute > "$HOME/minecraft-bedrock/admin-state/history-collector.log" 2>&1 # minecraft-performance-history
```

One cron invocation makes four collection attempts 15 seconds apart. The lock prevents overlapping collectors. Reading catalog or history data does not take the world-maintenance lock, and the collector does not restart the server or change its settings. Docker commands have timeouts; an unavailable Docker service produces missing readings, not fabricated metrics. A badly delayed collection may leave gaps.

The first database file is created with mode 600. New collector logs and lock files use a private umask. Old samples are deleted automatically after 30 days. Duplicate collection attempts in the same 15-second slot do not duplicate rows.

## Reading charts

The UI offers 1 hour, 6 hours, 24 hours, 7 days, and 30 days. Its time axis starts at the first available bucket in the selected window; the panel states when the history actually began. Historical data from before installation is not reconstructed.

The API returns roughly 240 buckets for large datasets. Aggregation preserves the minimum TPS and CPU peak, so brief *recorded* slowdowns are not averaged away. CPU's main line is the sample average, while its dashed line shows the peak. Memory and player charts show maxima. Unknown readings and missing buckets leave gaps in the curves.

The shared time slider supports keyboard inspection, and hovering over a graph selects the nearest recorded bucket. CSV export uses UTC timestamps and explicitly named aggregation columns. It exports the displayed buckets, not a separate stream of raw personal data.

The **lowest gameplay TPS** summary uses only samples with at least one player and a valid TPS reading. TPS dip records show the latest 20 samples below 18 TPS with players connected. These are recorded observations, not alerts or an inferred root cause. An idle world running at 20 TPS does not establish performance under load. A 15-second sampling schedule can also miss short stalls between samples.

The history view refreshes every minute; the existing live status panel keeps its own refresh interval. A missing or stale collector is indicated separately from the Minecraft server's running state.

## Validation

`test_history.py` covers retention, deduplication, unit conversion, multi-core CPU, stale and prior-run snapshots, missing readings, player-data exclusion, read-only empty history, aggregation preserving dips, active-player event filtering, export, and private file permissions on POSIX. `test_history_frontend.js` verifies chart segmentation across missing readings and gaps, as well as genuine zero values.
