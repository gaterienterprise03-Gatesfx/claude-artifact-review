//+------------------------------------------------------------------+
//| GatesFX_HD_UnitTests.mq5  (v1.1)                                 |
//| Run as a script on any chart in the live terminal.               |
//| Creates NEW folders HDU_* under Common\Files\                    |
//| GatesFX_HistoricalDiscovery\Runs. Touches nothing else.          |
//| Results: Experts log + unit_tests.csv in the HDU run folder.     |
//| NOT YET EXECUTED by the author - results must come from a real   |
//| terminal run.                                                    |
//+------------------------------------------------------------------+
#property copyright "GatesFX"
#property version   "1.10"

#include <GatesFX_HD\HD_Common.mqh>
#include <GatesFX_HD\HD_Persist.mqh>
#include <GatesFX_HD\HD_DataAudit.mqh>

CHDPersist g_t;
int g_pass = 0;
int g_fail = 0;

void T(const string name, const bool cond)
  {
   if(cond)
      g_pass++;
   else
      g_fail++;
   string line = HD_CsvField(name) + "," + (cond ? "PASS" : "FAIL");
   g_t.AppendLine("unit_tests.csv", line);
   Print("UT ", (cond ? "PASS " : "FAIL "), name);
  }

void SetSess(HD_Sessions &s)
  {
   s.known = true;
   for(int d = 0; d < 7; d++)
     {
      s.cnt[d] = 0;
      for(int i = 0; i < 10; i++)
        {
         s.from_s[d][i] = 0;
         s.to_s[d][i] = 0;
        }
     }
  }

void Add(HD_Sessions &s, const int d, const int from, const int to)
  {
   s.from_s[d][s.cnt[d]] = from;
   s.to_s[d][s.cnt[d]] = to;
   s.cnt[d]++;
  }

void TestSessions()
  {
   HD_Sessions s;
   SetSess(s);
   // Monday normal 08:00-17:00
   Add(s, 1, 8 * 3600, 17 * 3600);
   T("sess_normal_inside", HD_SessionContains(s, 1, 12 * 3600));
   T("sess_normal_start_inclusive", HD_SessionContains(s, 1, 8 * 3600));
   T("sess_normal_end_exclusive", !HD_SessionContains(s, 1, 17 * 3600));
   T("sess_normal_before", !HD_SessionContains(s, 1, 8 * 3600 - 1));
   T("sess_closed_day_tuesday", !HD_SessionContains(s, 2, 12 * 3600));
   // Tuesday overnight 22:00 -> 02:00 (to<from)
   Add(s, 2, 22 * 3600, 2 * 3600);
   T("sess_overnight_evening_in", HD_SessionContains(s, 2, 23 * 3600));
   T("sess_overnight_start_inclusive", HD_SessionContains(s, 2, 22 * 3600));
   T("sess_overnight_before_start_out", !HD_SessionContains(s, 2, 22 * 3600 - 1));
   T("sess_overnight_morning_next_day_in", HD_SessionContains(s, 3, 3600));
   T("sess_overnight_end_exclusive", !HD_SessionContains(s, 3, 2 * 3600));
   T("sess_overnight_same_day_morning_out", !HD_SessionContains(s, 2, 3600));
   // Wednesday two sessions, second ends at 24:00
   Add(s, 3, 6 * 3600, 9 * 3600);
   Add(s, 3, 20 * 3600, 86400);
   T("sess_multi_first", HD_SessionContains(s, 3, 7 * 3600));
   T("sess_multi_gap_out", !HD_SessionContains(s, 3, 12 * 3600));
   T("sess_multi_second_end_of_day", HD_SessionContains(s, 3, 86399));
   // 22:00 -> 00:00 (to==0 < from): evening only
   Add(s, 4, 22 * 3600, 0);
   T("sess_to_midnight_evening_in", HD_SessionContains(s, 4, 23 * 3600 + 3599));
   T("sess_to_midnight_no_morning", !HD_SessionContains(s, 5, 0));
   // Sunday->Monday wrap of previous-day lookup
   Add(s, 0, 23 * 3600, 3600);
   T("sess_sunday_overnight_into_monday", HD_SessionContains(s, 1, 1800));
   // Saturday overnight into Sunday
   Add(s, 6, 22 * 3600, 3600);
   T("sess_saturday_overnight_into_sunday", HD_SessionContains(s, 0, 1800));
   // zero-length ignored
   Add(s, 5, 9 * 3600, 9 * 3600);
   T("sess_zero_length_ignored", !HD_SessionContains(s, 5, 9 * 3600));
  }

void TestCommon()
  {
   uchar nine[];
   HD_StringToBytes("123456789", nine);
   T("crc32_known_vector", HD_Crc32(nine, 9) == 0xCBF43926);
   uchar a[], b[];
   HD_StringToBytes("1234", a);
   HD_StringToBytes("56789", b);
   uint st = HD_CrcUpdate(0xFFFFFFFF, a, 4);
   st = HD_CrcUpdate(st, b, 5);
   T("crc32_incremental_equals_whole", ~st == 0xCBF43926);
   uchar u[];
   int n = HD_StringToBytes("A" + ShortToString(0x00DC), u);
   T("utf8_two_byte_char", n == 3 && u[1] == 0xC3 && u[2] == 0x9C);

   T("csv_plain_unchanged", HD_CsvField("abc") == "abc");
   T("csv_comma_quoted", HD_CsvField("a,b") == "\"a,b\"");
   T("csv_quote_doubled", HD_CsvField("q\"x") == "\"q\"\"x\"");
   T("csv_newline_quoted", HD_CsvField("l1\nl2") == "\"l1\nl2\"");
   T("json_quote_backslash", HD_JsonEsc("a\"b\\c") == "a\\\"b\\\\c");
   T("json_newline_tab", HD_JsonEsc("x\ny\tz") == "x\\ny\\tz");
   T("json_control_01", HD_JsonEsc(ShortToString(1)) == "\\u0001");
   string odd = "Br\"oker, Ltd\n" + ShortToString(0x00DC) + "{\"k\":1}\\";
   string js = "{" + HD_JS("k", odd) + "\"z\":1}";
   string back = "";
   T("json_roundtrip_unusual_text", HD_JsonStr(js, "k", back) && back == odd);
   long v = 0;
   T("json_num_parse", HD_JsonNum("{\"a\":-12,\"b\":7}", "a", v) && v == -12);
   T("json_num_rejects_garbage", !HD_JsonNum("{\"a\":1x2}", "a", v));
   T("completion_gate_blocks_io_failure", !HD_CompletionMarkerAllowed(1, false) && !HD_CompletionMarkerAllowed(0, true) && HD_CompletionMarkerAllowed(0, false));
  }

void TestCsvLog()
  {
   CHDPersist p;
   if(!p.OpenNew("HDUL"))
     {
      T("csvlog_open_run", false);
      return;
     }
   CHDCsvLog log;
   T("csvlog_create", log.Create(p, "x.csv", "seq,a,b", 3));
   string odd = "has,comma \"and quote\"\nand newline";
   T("csvlog_append1", log.AppendRow("1,x," + HD_CsvField(odd)));
   uint crc1 = log.Crc();
   long b1 = log.Bytes();
   long r1 = log.Rows();
   T("csvlog_append2", log.AppendRow("2,y,z"));
   T("csvlog_verifysize", log.VerifySize());
   string err = "";
   long extra = 0;
   T("csvlog_prefix_validates_with_quoted_newline", HD_ValidateCsvPrefix(p.Path("x.csv"), 3, r1, b1, crc1, err, extra) && extra > 0);
   T("csvlog_prefix_wrong_crc_rejected", !HD_ValidateCsvPrefix(p.Path("x.csv"), 3, r1, b1, crc1 ^ 1, err, extra));
   T("csvlog_prefix_too_many_bytes_rejected", !HD_ValidateCsvPrefix(p.Path("x.csv"), 3, r1, log.Bytes() + 5, crc1, err, extra));
   T("csvlog_prefix_wrong_rows_rejected", !HD_ValidateCsvPrefix(p.Path("x.csv"), 3, r1 + 1, b1, crc1, err, extra));
   CHDPersist q;
   q.OpenNew("HDUL");
   CHDCsvLog r;
   T("csvlog_restore_prefix", r.Restore(q, HD_RUNS_DIR + "\\" + p.RunId(), "x.csv", 3, r1, b1, crc1, err) && r.Rows() == r1 && r.Bytes() == b1 && r.Crc() == crc1);
   T("csvlog_restored_continues", r.AppendRow("2,y,z") && r.Crc() == log.Crc() && r.Bytes() == log.Bytes());
  }

string Ck(const ulong seq, const string runId, const int fin, const long dqRows, const long dqBytes, const uint dqCrc,
          const string symbol)
  {
   string inner = HD_JN("schema", HD_SCHEMA_VERSION) + HD_JS("run_id", runId) + HD_JS("symbol", symbol) +
                  HD_JN("p_start", 100) + HD_JN("p_end", 200) + HD_JS("tf_cfg", "M1:60,M15:900") +
                  HD_JN("dq_rows", dqRows) + HD_JN("dq_bytes", dqBytes) + HD_JN("dq_crc", (long)dqCrc) +
                  HD_JN("acq_rows", 0) + HD_JN("acq_bytes", 0) + HD_JN("acq_crc", 0) +
                  "\"final\":" + IntegerToString(fin);
   return "{\"seq\":" + IntegerToString((long)seq) + "," + inner + "}";
  }

string CkFile(const string body, const bool corrupt)
  {
   uchar bb[];
   int bl = HD_StringToBytes(body, bb);
   string head = StringFormat("%08X", HD_Crc32(bb, bl));
   string b = body;
   if(corrupt)
      StringSetCharacter(b, 3, 'X');
   return head + "\n" + b;
  }

//--- make a fake parent with 3 dq rows; checkpoint states captured at 2 and 3 rows
bool MakeParent(CHDPersist &p, long &r2, long &b2, uint &c2, long &r3, long &b3, uint &c3, uint &acqCrc, long &acqBytes)
  {
   if(!p.OpenNew("HDUP"))
      return false;
   CHDCsvLog dq, aq;
   if(!dq.Create(p, "data_quality.csv", HD_DQ_HEADER, 9) || !aq.Create(p, "acquisition_failures.csv", HD_ACQ_HEADER, 8))
      return false;
   dq.AppendRow("1,M1,GAP,a,b,1,0,c,d");
   dq.AppendRow("2,M1,GAP,a,b,1,0,c,d");
   r2 = dq.Rows();
   b2 = dq.Bytes();
   c2 = dq.Crc();
   dq.AppendRow("3,M15,GAP,a,b,1,0,c,d");
   r3 = dq.Rows();
   b3 = dq.Bytes();
   c3 = dq.Crc();
   acqCrc = aq.Crc();
   acqBytes = aq.Bytes();
   return true;
  }

void TestResumeSelection()
  {
   long r2, b2, r3, b3, ab;
   uint c2, c3, ac;
   string body = "";
   ulong seq = 0;
   string rep = "";

   // S1: A(seq2) newest valid, B(seq1) older valid -> accept A
   CHDPersist p1;
   if(!MakeParent(p1, r2, b2, c2, r3, b3, c3, ac, ab)) { T("resume_setup", false); return; }
   p1.WriteTextVerified("checkpoint_A.json", CkFile(Ck(2, p1.RunId(), 0, r3, b3, c3, "XAUUSDz"), false));
   p1.WriteTextVerified("checkpoint_B.json", CkFile(Ck(1, p1.RunId(), 0, r2, b2, c2, "XAUUSDz"), false));
   T("resume_S1_prefers_newest_valid", HD_SelectResumeCheckpoint(p1.RunId(), "XAUUSDz", 100, 200, "M1:60,M15:900", body, seq, rep) && seq == 2);

   // S2: A corrupt, B valid -> accept B, rejection reported
   CHDPersist p2;
   MakeParent(p2, r2, b2, c2, r3, b3, c3, ac, ab);
   p2.WriteTextVerified("checkpoint_A.json", CkFile(Ck(2, p2.RunId(), 0, r3, b3, c3, "XAUUSDz"), true));
   p2.WriteTextVerified("checkpoint_B.json", CkFile(Ck(1, p2.RunId(), 0, r2, b2, c2, "XAUUSDz"), false));
   T("resume_S2_falls_back_to_valid_B", HD_SelectResumeCheckpoint(p2.RunId(), "XAUUSDz", 100, 200, "M1:60,M15:900", body, seq, rep) && seq == 1 && StringFind(rep, "A:REJECT") >= 0);

   // S3: both corrupt -> refuse
   CHDPersist p3;
   MakeParent(p3, r2, b2, c2, r3, b3, c3, ac, ab);
   p3.WriteTextVerified("checkpoint_A.json", CkFile(Ck(2, p3.RunId(), 0, r3, b3, c3, "XAUUSDz"), true));
   p3.WriteTextVerified("checkpoint_B.json", CkFile(Ck(1, p3.RunId(), 0, r2, b2, c2, "XAUUSDz"), true));
   T("resume_S3_both_corrupt_refused", !HD_SelectResumeCheckpoint(p3.RunId(), "XAUUSDz", 100, 200, "M1:60,M15:900", body, seq, rep));

   // S4: newest is FINAL (finalisation began) -> use older non-final
   CHDPersist p4;
   MakeParent(p4, r2, b2, c2, r3, b3, c3, ac, ab);
   p4.WriteTextVerified("checkpoint_A.json", CkFile(Ck(2, p4.RunId(), 1, r3, b3, c3, "XAUUSDz"), false));
   p4.WriteTextVerified("checkpoint_B.json", CkFile(Ck(1, p4.RunId(), 0, r2, b2, c2, "XAUUSDz"), false));
   T("resume_S4_skips_final_checkpoint", HD_SelectResumeCheckpoint(p4.RunId(), "XAUUSDz", 100, 200, "M1:60,M15:900", body, seq, rep) && seq == 1);

   // S5: newest valid by CRC but claims state the CSV cannot support -> rejected, older accepted
   CHDPersist p5;
   MakeParent(p5, r2, b2, c2, r3, b3, c3, ac, ab);
   p5.WriteTextVerified("checkpoint_A.json", CkFile(Ck(2, p5.RunId(), 0, r3 + 1, b3 + 20, c3, "XAUUSDz"), false));
   p5.WriteTextVerified("checkpoint_B.json", CkFile(Ck(1, p5.RunId(), 0, r2, b2, c2, "XAUUSDz"), false));
   T("resume_S5_csv_mismatch_rejected", HD_SelectResumeCheckpoint(p5.RunId(), "XAUUSDz", 100, 200, "M1:60,M15:900", body, seq, rep) && seq == 1);

   // S6: wrong symbol / period / identity -> refused
   T("resume_S6_symbol_mismatch_refused", !HD_SelectResumeCheckpoint(p1.RunId(), "EURUSD", 100, 200, "M1:60,M15:900", body, seq, rep));
   T("resume_S6_period_mismatch_refused", !HD_SelectResumeCheckpoint(p1.RunId(), "XAUUSDz", 101, 200, "M1:60,M15:900", body, seq, rep));
   T("resume_S6_tfcfg_mismatch_refused", !HD_SelectResumeCheckpoint(p1.RunId(), "XAUUSDz", 100, 200, "M1:60", body, seq, rep));

   // S7: truncated parent CSV (extra row cut) -> checkpoint claiming it is rejected
   CHDPersist p7;
   MakeParent(p7, r2, b2, c2, r3, b3, c3, ac, ab);
   p7.WriteTextVerified("checkpoint_A.json", CkFile(Ck(2, p7.RunId(), 0, r3, b3, c3, "XAUUSDz"), false));
   uchar all[];
   int n = p7.ReadAllBytes("data_quality.csv", all);
   uchar cut[];
   ArrayResize(cut, n - 10);
   ArrayCopy(cut, all, 0, 0, n - 10);
   p7.WriteBytesVerified("data_quality.csv", cut, n - 10);
   T("resume_S7_truncated_csv_refused", !HD_SelectResumeCheckpoint(p7.RunId(), "XAUUSDz", 100, 200, "M1:60,M15:900", body, seq, rep));
  }

void OnStart()
  {
   if(!g_t.OpenNew("HDU"))
     {
      Print("UT: cannot create results folder");
      return;
     }
   g_t.AppendLine("unit_tests.csv", "test,result");
   TestCommon();
   TestSessions();
   TestCsvLog();
   TestResumeSelection();
   string sum = "pass=" + IntegerToString(g_pass) + " fail=" + IntegerToString(g_fail);
   g_t.AppendLine("unit_tests.csv", "SUMMARY," + sum);
   Print("GatesFX HD unit tests: ", sum, " results in ", g_t.Dir());
  }
//+------------------------------------------------------------------+
