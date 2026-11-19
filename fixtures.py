"""Synthetic run-folder builder that mimics the EA's v1.1 output formats.
These fixtures test the PYTHON tools only. They are not output of the MQL5 EA."""
import csv
import io
import json
import os
import zlib

SCHEMA = 2
DQ_HEADER = ["seq", "timeframe", "event_type", "bar_time_a", "bar_time_b", "missing_bars",
             "missing_in_session_slots", "classification", "detail"]
ACQ_HEADER = ["seq", "timeframe", "interval_from", "interval_to", "error_code", "attempt",
              "disposition", "detail"]


def crc(b):
    return zlib.crc32(b) & 0xFFFFFFFF


def hexcrc(b):
    return "%08X" % crc(b)


def csv_bytes(header, rows):
    s = io.StringIO()
    w = csv.writer(s, lineterminator="\n")
    w.writerow(header)
    for r in rows:
        w.writerow(r)
    return s.getvalue().encode("utf-8")


def prefix_state(header, rows, n):
    b = csv_bytes(header, rows[:n])
    return {"rows": n, "bytes": len(b), "crc": crc(b)}


def ckpt_bytes(body):
    raw = json.dumps(body, separators=(",", ":")).encode("utf-8")
    return hexcrc(raw).encode("ascii") + b"\n" + raw


def tf_block(**kw):
    d = {"coverage_status": "BOUNDARIES_COVERED", "bars_audited": 1000, "duplicate_timestamps": 0,
         "out_of_order": 0, "misaligned_timestamps": 0, "ohlc_invalid_bars": 0, "nonpositive_price_bars": 0,
         "gaps_unexplained_or_unclassified": 0, "gaps_unchecked_long": 0, "acq_failures_unresolved": 0,
         "gaps_outside_current_schedule_unverified": 2, "first_bar_audited": "2024.11.19 00:00:00",
         "last_bar_audited": "2026.11.18 23:45:00", "bar_digest_crc32": "ABCDEF01", "gap_events": 2,
         "missing_bars_total": 10}
    d.update(kw)
    return d


def make_run(root, name, *, status="FINALISED_CLEAN", completion=True, m1=None, m15=None,
             acquisition_complete=1, io_failures=0, suitability="PROVISIONAL_PENDING_CLOSURE_REVIEW",
             suppressed=0, odd_text=False, log_text=None, init_failed=False, ckpts="clean_final",
             tamper=None, partial_tail=False):
    rdir = os.path.join(root, "Runs", name)
    os.makedirs(rdir)
    detail = 'has,comma "quote"\nnewline' if odd_text else "d"
    dq_rows = [[str(i), "M1", "GAP", "a", "b", "1", "0", "c", detail] for i in range(1, 4)]
    acq_rows = []
    dq = csv_bytes(DQ_HEADER, dq_rows)
    aq = csv_bytes(ACQ_HEADER, acq_rows)
    with open(os.path.join(rdir, "data_quality.csv"), "wb") as f:
        f.write(dq + (b"4,M1,GAP,a" if partial_tail else b""))
    with open(os.path.join(rdir, "acquisition_failures.csv"), "wb") as f:
        f.write(aq)
    man = {"schema": SCHEMA, "run_id": name, "status": status if completion or ckpts == "final_then_crash" else "STARTED",
           "broker_company": 'Brök"er, Ltd\n(test)' if odd_text else "Broker",
           "event_rows_suppressed_by_cap": suppressed, "suitability": suitability,
           "suitability_reasons": "x", "acquisition_complete": acquisition_complete, "io_failures": io_failures,
           "data_quality": {"M1": m1 or tf_block(), "M15": m15 or tf_block()}}
    man_raw = json.dumps(man, ensure_ascii=False).encode("utf-8")
    with open(os.path.join(rdir, "manifest.json"), "wb") as f:
        f.write(man_raw)
    s2 = prefix_state(DQ_HEADER, dq_rows, 3)
    s1 = prefix_state(DQ_HEADER, dq_rows, 2)
    a0 = prefix_state(ACQ_HEADER, acq_rows, 0)

    def body(seq, st, final):
        return {"seq": seq, "schema": SCHEMA, "run_id": name, "symbol": "XAUUSDz", "p_start": 100, "p_end": 200,
                "tf_cfg": "M1:60,M15:900", "dq_rows": st["rows"], "dq_bytes": st["bytes"], "dq_crc": st["crc"],
                "acq_rows": a0["rows"], "acq_bytes": a0["bytes"], "acq_crc": a0["crc"], "final": final}

    if ckpts == "clean_final":
        with open(os.path.join(rdir, "checkpoint_A.json"), "wb") as f:
            f.write(ckpt_bytes(body(2, s2, 1)))
        with open(os.path.join(rdir, "checkpoint_B.json"), "wb") as f:
            f.write(ckpt_bytes(body(1, s1, 0)))
    elif ckpts == "periodic":          # interrupted between checkpoints
        with open(os.path.join(rdir, "checkpoint_A.json"), "wb") as f:
            f.write(ckpt_bytes(body(2, s2, 0)))
        with open(os.path.join(rdir, "checkpoint_B.json"), "wb") as f:
            f.write(ckpt_bytes(body(1, s1, 0)))
    elif ckpts == "final_then_crash":  # interrupted during finalisation (final ckpt written, no completion)
        with open(os.path.join(rdir, "checkpoint_A.json"), "wb") as f:
            f.write(ckpt_bytes(body(2, s2, 1)))
        with open(os.path.join(rdir, "checkpoint_B.json"), "wb") as f:
            f.write(ckpt_bytes(body(1, s1, 0)))
    elif ckpts == "both_corrupt":
        for n, sq, st in (("checkpoint_A.json", 2, s2), ("checkpoint_B.json", 1, s1)):
            raw = bytearray(ckpt_bytes(body(sq, st, 0)))
            raw[20] ^= 0xFF
            with open(os.path.join(rdir, n), "wb") as f:
                f.write(bytes(raw))
    elif ckpts == "none":
        pass
    if completion:
        comp = {"schema": SCHEMA, "run_id": name, "status": status, "manifest_crc32": hexcrc(man_raw),
                "dq_rows": 3, "dq_csv_bytes": len(dq), "dq_csv_crc32": hexcrc(dq),
                "acq_rows": 0, "acq_csv_bytes": len(aq), "acq_csv_crc32": hexcrc(aq),
                "io_failures": io_failures, "acquisition_complete": acquisition_complete,
                "suitability": suitability}
        with open(os.path.join(rdir, "completion.json"), "w") as f:
            json.dump(comp, f)
    if init_failed:
        with open(os.path.join(rdir, "init_failed.txt"), "w") as f:
            f.write("x")
    if log_text:
        with open(os.path.join(rdir, "execution.log"), "w") as f:
            f.write(log_text)
    if tamper:
        tamper(rdir)
    return rdir


def rd(path):
    with open(path, "rb") as f:
        return f.read()


def wr(path, data):
    with open(path, "wb") as f:
        f.write(data)
