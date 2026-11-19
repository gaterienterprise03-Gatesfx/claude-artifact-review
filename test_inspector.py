import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))
import fixtures as fx          # noqa: E402
import hd_inspect_runs as ins  # noqa: E402


class InspectorTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def verdict(self, name, **kw):
        rdir = fx.make_run(self.root, name, **kw)
        v, reasons = ins.inspect_run(rdir)
        return v, " | ".join(reasons)

    # ---- positive
    def test_clean_run_is_complete_verified(self):
        v, r = self.verdict("clean")
        self.assertEqual(v, "COMPLETE_VERIFIED", r)
        self.assertIn("UNVERIFIED", r)  # closures always flagged for human confirmation

    def test_unusual_text_still_parses(self):
        v, r = self.verdict("odd", odd_text=True)
        self.assertEqual(v, "COMPLETE_VERIFIED", r)

    # ---- negative: none of these may ever be COMPLETE_VERIFIED
    def test_io_failure_status_is_failed(self):
        v, r = self.verdict("io", status="FINALISED_AFTER_IO_FAILURE", io_failures=2)
        self.assertEqual(v, "FAILED", r)

    def test_io_failure_in_completion_counter(self):
        v, r = self.verdict("io2", io_failures=1)
        self.assertEqual(v, "FAILED", r)

    def test_withheld_marker_in_log_is_failed(self):
        v, r = self.verdict("log", completion=False, ckpts="periodic",
                            log_text="x|ERROR|finalisation I/O failures; completion marker withheld\n")
        self.assertEqual(v, "FAILED", r)

    def test_init_failed_is_failed(self):
        v, r = self.verdict("init", completion=False, ckpts="none", init_failed=True)
        self.assertEqual(v, "FAILED", r)

    def test_acquisition_incomplete_status(self):
        v, r = self.verdict("acq", status="FINALISED_INCOMPLETE_ACQUISITION", acquisition_complete=0,
                            m15=fx.tf_block(acq_failures_unresolved=1))
        self.assertEqual(v, "INCOMPLETE", r)

    def test_clean_status_with_acquisition_incomplete_is_contradiction(self):
        v, r = self.verdict("contra", acquisition_complete=0)
        self.assertEqual(v, "CORRUPT", r)

    def test_unresolved_acq_in_manifest_blocks(self):
        v, r = self.verdict("unres", m1=fx.tf_block(acq_failures_unresolved=2))
        self.assertNotEqual(v, "COMPLETE_VERIFIED", r)
        self.assertEqual(v, "INCOMPLETE", r)

    def test_partial_coverage_is_incomplete(self):
        v, r = self.verdict("cov", m15=fx.tf_block(coverage_status="PARTIAL_END"))
        self.assertEqual(v, "INCOMPLETE", r)

    def test_data_defects_need_review(self):
        v, r = self.verdict("def", m1=fx.tf_block(duplicate_timestamps=3),
                            suitability="NOT_SUITABLE")
        self.assertEqual(v, "NEEDS_REVIEW", r)

    def test_unexplained_gaps_need_review(self):
        v, r = self.verdict("gap", m15=fx.tf_block(gaps_unexplained_or_unclassified=4), suitability="NEEDS_REVIEW")
        self.assertEqual(v, "NEEDS_REVIEW", r)

    def test_suppressed_events_need_review(self):
        v, r = self.verdict("supp", suppressed=10, suitability="NEEDS_REVIEW")
        self.assertEqual(v, "NEEDS_REVIEW", r)

    def test_tampered_csv_is_corrupt(self):
        def t(rdir):
            p = os.path.join(rdir, "data_quality.csv")
            b = bytearray(fx.rd(p))
            b[40] ^= 0x01
            fx.wr(p, bytes(b))
        v, r = self.verdict("tcsv", tamper=t)
        self.assertEqual(v, "CORRUPT", r)

    def test_truncated_csv_is_corrupt(self):
        def t(rdir):
            p = os.path.join(rdir, "data_quality.csv")
            b = fx.rd(p)
            fx.wr(p, b[:-5])
        v, r = self.verdict("trunc", tamper=t)
        self.assertEqual(v, "CORRUPT", r)

    def test_tampered_manifest_is_corrupt(self):
        def t(rdir):
            p = os.path.join(rdir, "manifest.json")
            fx.wr(p, fx.rd(p) + b" ")
        v, r = self.verdict("tman", tamper=t)
        self.assertEqual(v, "CORRUPT", r)

    def test_unreadable_completion_is_corrupt(self):
        def t(rdir):
            fx.wr(os.path.join(rdir, "completion.json"), b"{not json")
        v, r = self.verdict("tcomp", tamper=t)
        self.assertEqual(v, "CORRUPT", r)

    def test_missing_checkpoints_with_completion_is_corrupt(self):
        v, r = self.verdict("nock", ckpts="none")
        self.assertEqual(v, "CORRUPT", r)

    # ---- interrupted runs (before first checkpoint is covered by 'none' below)
    def test_interrupted_between_checkpoints_is_incomplete_and_resumable(self):
        v, r = self.verdict("int", completion=False, ckpts="periodic", partial_tail=True)
        self.assertEqual(v, "INCOMPLETE", r)
        self.assertIn("RESUMABLE", r)
        self.assertNotIn("NOT RESUMABLE", r)

    def test_interrupted_during_finalisation_resumes_from_older_checkpoint(self):
        v, r = self.verdict("fin", status="FINALISED_CLEAN", completion=False, ckpts="final_then_crash")
        self.assertEqual(v, "INCOMPLETE", r)
        self.assertIn("seq=1", r)
        self.assertIn("skipped: final checkpoint", r)

    def test_both_checkpoints_corrupt_not_resumable(self):
        v, r = self.verdict("bc", completion=False, ckpts="both_corrupt")
        self.assertEqual(v, "INCOMPLETE", r)
        self.assertIn("NOT RESUMABLE", r)

    def test_no_checkpoint_yet_not_resumable(self):
        v, r = self.verdict("early", completion=False, ckpts="none")
        self.assertEqual(v, "INCOMPLETE", r)
        self.assertIn("NOT RESUMABLE", r)

    def test_one_corrupt_checkpoint_falls_back(self):
        def t(rdir):
            p = os.path.join(rdir, "checkpoint_A.json")
            b = bytearray(fx.rd(p))
            b[25] ^= 0xFF
            fx.wr(p, bytes(b))
        v, r = self.verdict("onebad", completion=False, ckpts="periodic", tamper=t)
        self.assertEqual(v, "INCOMPLETE", r)
        self.assertIn("checkpoint_A.json rejected", r)
        self.assertIn("RESUMABLE", r)

    def test_checkpoint_claiming_more_rows_than_csv_rejected(self):
        def t(rdir):
            p = os.path.join(rdir, "data_quality.csv")
            b = fx.rd(p)
            fx.wr(p, b[:-12])
        v, r = self.verdict("shortcsv", completion=False, ckpts="periodic", tamper=t)
        self.assertEqual(v, "INCOMPLETE", r)
        self.assertIn("shorter than checkpoint claims", r)

    def test_never_complete_for_any_negative_case(self):
        cases = [dict(status="FINALISED_AFTER_IO_FAILURE", io_failures=1),
                 dict(completion=False, ckpts="periodic"),
                 dict(status="FINALISED_INCOMPLETE_ACQUISITION", acquisition_complete=0),
                 dict(m1=fx.tf_block(coverage_status="NONE")),
                 dict(init_failed=True)]
        for i, kw in enumerate(cases):
            v, r = self.verdict("neg%d" % i, **kw)
            self.assertNotEqual(v, "COMPLETE_VERIFIED", r)


if __name__ == "__main__":
    unittest.main(verbosity=2)
