# GatesFX Historical Discovery – Stage 1 v1.1: Change Log and Verification Report

**Read this first.** v1.1 is a corrected *source* package. **Nothing in it has been compiled in MetaEditor or executed in MetaTrader.** This environment has no MT5, no broker history and no network. The only code that was actually executed is the Python tooling (34 tests, all passing; see section 3). Every MQL5 claim below is "written / statically inspected", not "tested".

v1.0 remains untouched in `GatesFX_HD_Stage1/` (hashes recorded and re-verified: 5/5 OK). v1.1 lives in `GatesFX_HD_Stage1_v1.1/`. No existing GatesFX file was read or modified. No trading code exists in either version (static scan: no `OrderSend`, `CTrade`, `WebRequest`, `#import`).

## 1. Evidence levels used in this report

| Level | Meaning | Status in this package |
|---|---|---|
| Static inspection | Read/scanned only | Done (bracket balance, forbidden-construct scan, symbol cross-reference, CRC algorithm vs zlib) |
| Compilation | MetaEditor build, 0 errors / 0 warnings | **NOT DONE** (needs your PC) |
| Unit tests (Python) | Executed here | **DONE: 34/34 pass** |
| Unit tests (MQL5) | `GatesFX_HD_UnitTests.mq5` | **Written, NOT executed** |
| Integration tests (tester/terminal) | T1–T12 in INSTALL_AND_TEST.md | **NOT EXECUTED** |

## 2. Defect-by-defect

### D1 History acquisition failures treated as fatal or incomplete
- **Files/functions:** `GatesFX_HistoricalDiscovery.mq5`: `PollTf`, `HandleAcqFailure`, `RecordAcq`, `OnTick`, `Finalise`, `BuildManifest`; `HD_DataAudit.mqh`: `HD_TfAudit` acquisition fields, `HD_AuditCk/Restore`; probe script `AuditRange`.
- **Root cause (v1.0):** a failed `CopyRates` only incremented a counter and returned; `OnTick` continued and `Finalise` could still emit a normal completion.
- **Correction:** every fetch is checked against `Bars()` (`CopyRates` count must equal expected). Mismatch = failure: the watermark (`last_fetched`) and bar state are **not** advanced. Failures are classified temporary (`SERIES_SYNCHRONIZED==0`, tolerated up to `InpAcqMaxNotReady` polls) or counted toward `InpAcqMaxRetries`. Exhausted retries = `UNRESOLVED_FATAL`: processing stops, a resumable (non-final) checkpoint is written, status becomes `FINALISED_INCOMPLETE_ACQUISITION`. Each attempt is persisted in `acquisition_failures.csv` (timeframe, interval, error code, attempt, disposition, detail); later success logs `RESOLVED_AFTER_RETRY`. Manifest/completion carry `acquisition_complete`. Probe script retries each chunk and records empty/failed chunks as `UNRESOLVED_*`.
- **Not implemented:** wall-clock timeouts (`Sleep` is unreliable in the tester); retries are count-based only. A zero-bar range is deliberately *not* an acquisition event for the EA (it cannot be told apart from a weekend); real holes surface as GAP events.
- **Tests:** Python: `test_acquisition_incomplete_status`, `test_clean_status_with_acquisition_incomplete_is_contradiction`, `test_unresolved_acq_in_manifest_blocks`. MQL5 integration (injecting history failures): **not possible to simulate reliably in the tester**; documented as a manual scenario (T9).

### D2 Overnight sessions classified incorrectly
- **Files/functions:** `HD_DataAudit.mqh`: new `HD_SessionContains`, `HD_InSession`.
- **Root cause:** `sod >= from && sod < to` matches nothing when `to < from`.
- **Correction:** start inclusive/end exclusive; `to<from` = overnight (evening part on the listed day, morning part on the next day, week-wrapped); multiple sessions per day; `to` clamped to 86400; `to==from` zero-length (ignored, documented). Gap class renamed `OUTSIDE_CURRENT_SCHEDULE_UNVERIFIED`; the disclosure that the schedule is current, not historical, is kept in manifest and gap detail.
- **Tests:** MQL5 `TestSessions` (21 cases: normal, boundaries, closed day, overnight both sides, multi-session, end-of-day, to-midnight, Sunday/Saturday wrap, zero-length) **not executed**. Python mirror `session_reference.py` + 7 tests **executed, pass**; includes a test demonstrating the v1.0 logic fails the overnight case. The mirror verifies the algorithm/vectors only, not the MQL5 code.

### D3 Inspector accepted failed runs
- **File:** `Tools/hd_inspect_runs.py` (rewritten).
- **Correction:** five explicit verdicts (CORRUPT > FAILED > INCOMPLETE > NEEDS_REVIEW > COMPLETE_VERIFIED), each with itemised reasons. COMPLETE_VERIFIED requires: completion marker; manifest CRC; both CSV sizes/CRCs/row counts/headers/field counts/sequence continuity; a valid final checkpoint consistent with completion; manifest-vs-completion status agreement; `io_failures==0`; `acquisition_complete==1`; both timeframes `BOUNDARIES_COVERED`; no data defects, unexplained or unchecked gaps, suppressed events; suitability provisional. Unverified closures are always listed.
- **Tests (executed):** 25 inspector tests incl. negative tests proving FINALISED_AFTER_IO_FAILURE, init failure, withheld marker, acquisition incomplete, partial coverage, tampered/truncated CSV, tampered manifest, unreadable completion, missing checkpoints are never COMPLETE_VERIFIED (`test_never_complete_for_any_negative_case` loops over five failure types).

### D4 Resume correctness
- **Files/functions:** `HD_Persist.mqh`: `HD_ReadCheckpoint`, `HD_SelectResumeCheckpoint`, `HD_ValidateCsvPrefix`, `CHDCsvLog::Restore`; EA `OnInit`.
- **Correction:** checkpoint carries schema, run_id, parent_run_id, lineage, EA version, tf config, symbol, period, per-log rows/bytes/CRC, per-timeframe bar **digest** (CRC over every audited bar's time/OHLC/volume/spread). Selection policy: invalid checkpoints (CRC, schema, parity, missing fields) are rejected **and reported**; final checkpoints are skipped; identity/symbol/period/tf-config must match; the parent's CSV prefix must match the checkpoint's rows, bytes, CRC, field counts and sequence; otherwise fall back to the older checkpoint. Both bad = resume refused (`INIT_FAILED`, new run folder marked `init_failed.txt`, parent untouched). Bytes beyond the checkpoint in the parent are never copied (events are re-detected on replay) and the parent keeps them. The resumed run is a **new** folder with `parent_run_id`, `lineage`, `parent_checkpoint_seq`, `resume_selection_report`. Digest + counters make duplicated or omitted bars detectable by comparing against an uninterrupted run.
- **Tests:** MQL5 `TestResumeSelection` S1–S7 (newest valid, corrupt A, both corrupt, final skipped, CSV mismatch, identity mismatches, truncated CSV) **not executed**. Python: `test_one_corrupt_checkpoint_falls_back`, `test_both_checkpoints_corrupt_not_resumable`, `test_checkpoint_claiming_more_rows_than_csv_rejected`, `test_interrupted_during_finalisation_resumes_from_older_checkpoint` **executed, pass**. The uninterrupted-vs-resumed equality comparison is **not yet demonstrated** (needs real runs; tool `hd_run_tools.py compare` is ready and tested on synthetic data only).
- During the work, a defect in my own first v1.1 draft was found by a Python test (rejected checkpoints were not reported when a newer valid one existed) and fixed in both the MQL5 selector and the Python mirror.

### D5 Interrupted-run semantics
- **Correction:** completion is established only by `completion.json`, written last and only if no persistence failure is outstanding (`HD_CompletionMarkerAllowed`). Test abort modes: 1 before first periodic checkpoint, 2 between checkpoints, 3 mid-finalisation (after final checkpoint + summary), 4 mid-finalisation (after manifest, before completion). All leave the run INCOMPLETE and identifiable. Resume refuses final checkpoints, so modes 3/4 recover from the older checkpoint. Documented procedure in INSTALL_AND_TEST.md section 5.
- **Tests:** Python: interrupted between checkpoints, during finalisation, no checkpoint yet, both corrupt (all executed). MQL5 abort modes: **not executed** (T3–T6).

### D6 Event persistence integrity
- **Files:** `HD_Persist.mqh` `HD_AppendAbsSized`, `CHDCsvLog` (running CRC/bytes/rows, size check after every append, `VerifySize`), `HD_ValidateCsvBytes`; `HD_DataAudit.mqh` `HD_WriteEvents`.
- **Correction:** each append compares the real file size to the expected size (detects partial/failed/foreign writes); checkpoint rows/bytes/CRC come from the log object and `VerifySize` runs before every checkpoint; recovery and the inspector reject truncated, malformed, wrong-width or sequence-broken CSV; rows are append-only (never rewritten); cap: one `EVENT_CAP_REACHED` marker row, suppressed count kept in checkpoint/manifest/summary, counters stay complete.
- **Tests:** MQL5 `TestCsvLog` and self-test T8 **not executed**; Python CSV validation covered via inspector tests (executed).

### D7 Period and timestamp semantics
- **Correction:** manifest states `period_timebase` = broker server time, no UTC conversion; samples `TimeCurrent()-TimeGMT()` per processed M15 batch (first/min/max/last/changes) as *observation only*; per-timeframe requested vs observed first/last bar, shortfalls, `coverage_status` (`BOUNDARIES_COVERED`, `PARTIAL_START`, `PARTIAL_END`, `PARTIAL_START_AND_END`, `NONE`) with tolerance `InpCoverageToleranceHours`; `coverage_basis` text says it reflects first/last bar only, not interior completeness.
- **Limitation:** the historical broker UTC offset cannot be verified from inside MQL5; offset samples inside the tester may not reflect real history.

### D8 CSV and JSON output integrity
- **Correction:** `HD_CsvField` (RFC-4180 quoting for comma, quote, CR, LF) applied to every text field in every CSV; `HD_JsonEsc` escapes quote, backslash and all control characters (<0x20, `\uXXXX`); UTF-8 byte conversion (v1.0 replaced non-ASCII with `?`); log lines pipe/newline-safe; Python inspector parses with `csv`/`json` strictly.
- **Tests:** MQL5 `TestCommon` (CSV/JSON escape vectors, JSON string round-trip with quotes, commas, newline, non-ASCII, backslash, JSON-like text) **not executed**. Python: `test_unusual_text_still_parses` (executed) parses a manifest with a broker name containing a quote, comma, newline and non-ASCII plus a CSV detail with comma/quote/newline.

### D9 Filesystem self-test coverage
- **Correction:** `SelfTest` now covers write/flush/reopen/CRC, sized appends, FileMove-rewrite, corrupt-checkpoint detection (good / bad CRC / flipped byte / wrong parity), unavailable-path failure detection, leftover `.tmp` replace, and CSV truncation/column/sequence detection. Injected failures are expected and do not poison the run's failure counter. A failed self-test blocks the run. `NOT_SIMULATED` is recorded in the report: disk full, permission revoked mid-run, power loss mid-write cannot be reliably simulated in MetaTrader. Failed persistence prevents the completion marker (`HD_CompletionMarkerAllowed`, unit-tested in MQL5 `TestCommon`, not executed).

### D10 Completeness reporting
- **Correction:** summary/manifest report requested vs observed period, first/last bar, coverage per timeframe, acquisition failures separately from gaps, unclassified/unchecked long gaps, and a derived `suitability`: `NOT_SUITABLE` / `NEEDS_REVIEW` / `PROVISIONAL_PENDING_CLOSURE_REVIEW`. It is **never** a plain "suitable": closures outside the current schedule are explicitly unverified.

## 3. Executed test evidence (Python only)

Command (from `Tools/`): `python3 -W error::ResourceWarning -m unittest discover -s tests -v`
Actual result of the last run: `Ran 34 tests ... OK` (25 inspector, 7 session-mirror, 2 run-tools). Fixtures are synthetic (generated by `tests/fixtures.py`) and test the Python tools only.

Other executed checks: CRC-32 loop port gives `CBF43926` for `123456789` both whole and incremental, equal to `zlib.crc32`. v1.0 hash re-check: 5/5 OK.

## 4. Not done / unresolved

- Compilation (errors **and warnings**) of all three MQL5 programs: not done. Likely trouble spots to watch: implicit conversions, `GetPointer` on reference params, ternary expressions mixing types, struct arrays with strings.
- MQL5 unit tests, integration tests, interruption tests, resumed-vs-uninterrupted comparison: not executed.
- Declared vs verified tester modelling mode: the manifest labels the mode as declared and `modelling_mode_verified` = "NO". Independent verification requires the tester report/journal from your run.
- SHA-256: provided externally (`--sha256`, `hd_run_tools.py hash/verify`); the EA itself uses CRC-32 only (MQL5 `CryptEncode` could add in-EA SHA-256; not implemented).
- Raw/canonical dataset export and all of Gates C–G: **not started** (see section 5).
- Possible false acquisition failures: the strict `CopyRates == Bars` equality has never been run against a real terminal.

## 5. Assignment gates

| Gate | Status |
|---|---|
| A Acquisition and persistence corrections | Source written; runtime-unverified |
| B Compilation and independent testing | **Blocked: needs your PC** (MetaEditor, Strategy Tester); Python part done |
| C Historical acquisition | Not started; needs broker history in your terminal; this environment has none and no network |
| D Dataset validation/construction | Not started; depends on C (and on a raw-bar exporter, not yet written) |
| E Behaviour discovery | Not started; depends on D |
| F Statistical evaluation / out-of-sample | Not started; depends on E |
| G Final report and reproducibility package | Not started |

Per your own rule, I did not advance past an unverified gate. No data, no candidate behaviours, no expectancy results exist; none are claimed.

## 6. Package integrity

`MANIFEST_SHA256.json` lists every file in this package with size and SHA-256.
