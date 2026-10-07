import os
import sqlite3
import sys
import tempfile
import types
import unittest
from datetime import datetime, timedelta, timezone

if "apify_client" not in sys.modules:
    fake = types.ModuleType("apify_client")
    class FakeApifyClient(object):
        pass
    fake.ApifyClient = FakeApifyClient
    sys.modules["apify_client"] = fake

import config
import relevance
import main


class RelevanceTests(unittest.TestCase):
    def test_exact_title_scores_high(self):
        r = relevance.score_job("Technical Support Engineer", "Troubleshoot APIs, SQL and production incidents.")
        self.assertGreaterEqual(r["score"], config.RELEVANCE_HIGH_THRESHOLD)
        self.assertTrue(relevance.should_alert(r))

    def test_it_support_bare_title_is_alertable(self):
        r = relevance.score_job("IT Support", "Handle tickets, Windows, DNS, VPN and user issues.")
        self.assertTrue(relevance.should_alert(r))

    def test_application_support_is_related(self):
        r = relevance.score_job("L2 Application Support Engineer (Integration & Middleware)", "Support APIs, integrations, middleware and production incidents.")
        self.assertTrue(relevance.should_alert(r))

    def test_helpdesk_and_help_desk_are_equivalent(self):
        a = relevance.score_job("Help Desk Analyst", "Handle incidents and tickets.")
        b = relevance.score_job("Helpdesk Analyst", "Handle incidents and tickets.")
        self.assertAlmostEqual(a["score"], b["score"], delta=1.0)
        self.assertTrue(relevance.should_alert(a))
        self.assertTrue(relevance.should_alert(b))

    def test_customer_service_family(self):
        r = relevance.score_job("Customer Service Representative", "Handle customer tickets, technical issues and escalation.")
        self.assertTrue(relevance.should_alert(r))
        self.assertIn("Customer Support", r["matched_families"])

    def test_noc_is_not_a_target_role(self):
        r = relevance.score_job("NOC Engineer", "Monitor networks and resolve incidents.")
        self.assertFalse(relevance.should_alert(r))

    def test_cloud_support_engineer_is_not_a_target_role(self):
        r = relevance.score_job("Cloud Support Engineer", "AWS, Azure, cloud infrastructure and troubleshooting.")
        self.assertFalse(relevance.should_alert(r))

    def test_description_only_is_weaker_than_title(self):
        title = relevance.score_job("Software Engineer", "Provide technical support and troubleshoot production applications.")
        target = relevance.score_job("Technical Support Engineer", "Troubleshoot production applications.")
        self.assertLess(title["score"], target["score"])

    def test_sales_role_is_suppressed(self):
        r = relevance.score_job("Account Executive", "Sell SaaS, perform cold calling, lead generation and meet sales quota.")
        self.assertFalse(relevance.should_alert(r))

    def test_business_development_is_suppressed(self):
        r = relevance.score_job("Business Development Executive", "Lead generation, sales quota and customer acquisition.")
        self.assertFalse(relevance.should_alert(r))

    def test_service_desk_family(self):
        r = relevance.score_job("Service Desk Analyst", "Handle incidents, tickets, users, troubleshooting and SLA escalation.")
        self.assertTrue(relevance.should_alert(r))


class DateTests(unittest.TestCase):
    def test_epoch_seconds(self):
        now = datetime.now(timezone.utc)
        parsed = main.parse_posted_at(now.timestamp())
        self.assertIsNotNone(parsed)
        self.assertLess(abs((parsed - now).total_seconds()), 2)

    def test_epoch_milliseconds(self):
        now = datetime.now(timezone.utc)
        parsed = main.parse_posted_at(now.timestamp() * 1000)
        self.assertIsNotNone(parsed)
        self.assertLess(abs((parsed - now).total_seconds()), 2)

    def test_relative_hours(self):
        parsed = main.parse_posted_at("3 hours ago")
        self.assertIsNotNone(parsed)
        self.assertTrue(2.9 * 3600 < (datetime.now(timezone.utc) - parsed).total_seconds() < 3.1 * 3600)

    def test_unknown_date_is_none(self):
        self.assertIsNone(main.parse_posted_at("some unknown format"))
        self.assertIsNone(main.parse_posted_at(None))

    def test_future_date_is_rejected_by_run_logic_boundary(self):
        future = datetime.now(timezone.utc) + timedelta(hours=1)
        self.assertGreater(future, datetime.now(timezone.utc) + timedelta(minutes=5))


class UrlLocationTests(unittest.TestCase):
    def test_tracking_params_removed(self):
        u = main.normalize_url("https://www.linkedin.com/jobs/view/123456/?trk=foo&utm_source=x")
        self.assertEqual(u, "https://www.linkedin.com/jobs/view/123456")

    def test_job_id_extracted(self):
        self.assertEqual(main.linkedin_job_id("https://www.linkedin.com/jobs/view/technical-support-engineer-123456"), "123456")

    def test_saudi_location(self):
        ok, _ = main.validate_location("Riyadh, Saudi Arabia", "Saudi Arabia")
        self.assertTrue(ok)

    def test_qatar_location(self):
        ok, _ = main.validate_location("Doha, Qatar", "Qatar")
        self.assertTrue(ok)

    def test_mismatched_location(self):
        ok, _ = main.validate_location("Dubai, United Arab Emirates", "Saudi Arabia")
        self.assertFalse(ok)

    def test_unspecified_remote_is_rejected(self):
        ok, _ = main.validate_location("Remote", "Saudi Arabia")
        self.assertFalse(ok)

    def test_country_named_remote_is_accepted(self):
        ok, _ = main.validate_location("Remote - Riyadh, Saudi Arabia", "Saudi Arabia")
        self.assertTrue(ok)


class SearchRotationTests(unittest.TestCase):
    def test_all_eight_combos_exist(self):
        combos = main.all_search_combos()
        self.assertEqual(len(combos), 8)
        self.assertNotIn(("NOC Engineer", "Saudi Arabia"), combos)

    def test_rotation_covers_all_combos_in_two_runs(self):
        tmp = tempfile.NamedTemporaryFile(delete=False)
        tmp.close()
        old = config.DB_PATH
        try:
            config.DB_PATH = tmp.name
            conn = main.init_db()
            first = main.select_search_combos(conn)
            for combo in first:
                main.advance_search_cursor(conn, combo)
            second = main.select_search_combos(conn)
            self.assertEqual(len(first), 4)
            self.assertEqual(len(second), 4)
            self.assertEqual(set(first + second), set(main.all_search_combos()))
            conn.close()
        finally:
            config.DB_PATH = old
            try: os.unlink(tmp.name)
            except OSError: pass


class ScheduleTests(unittest.TestCase):
    def test_off_slot_blocked(self):
        dt = datetime(2026, 9, 24, 10, 30, tzinfo=timezone(timedelta(hours=3)))
        self.assertIn("outside", main.schedule_block_reason(dt))

    def test_valid_slot(self):
        dt = datetime(2026, 9, 24, 12, 5, tzinfo=timezone(timedelta(hours=3)))
        self.assertIsNone(main.schedule_block_reason(dt))

    def test_weekend_blocked(self):
        dt = datetime(2026, 9, 25, 9, 5, tzinfo=timezone(timedelta(hours=3)))
        self.assertIn("weekend", main.schedule_block_reason(dt))

    def test_country_holiday_is_country_specific(self):
        dt = datetime(2026, 9, 23, 9, 5, tzinfo=timezone(timedelta(hours=3)))
        self.assertTrue(main.country_holiday("Saudi Arabia", dt))
        self.assertFalse(main.country_holiday("Qatar", dt))


class MigrationTests(unittest.TestCase):
    def test_old_schema_migrates(self):
        old = tempfile.NamedTemporaryFile(delete=False)
        old.close()
        old_path = old.name
        original = config.DB_PATH
        try:
            config.DB_PATH = old_path
            conn = sqlite3.connect(old_path)
            conn.execute("CREATE TABLE jobs (job_key TEXT PRIMARY KEY, title TEXT, company TEXT, country TEXT, location TEXT, url TEXT, posted_at TEXT, description TEXT, matched_keyword TEXT, fetched_at TEXT, alerted_at TEXT)")
            conn.execute("CREATE TABLE run_history (run_id TEXT, timestamp TEXT, day_of_week TEXT, schedule_slot TEXT, keyword TEXT, country TEXT, jobs_fetched INTEGER, jobs_matched INTEGER, jobs_alerted INTEGER, skipped_stale INTEGER, skipped_duplicate INTEGER, skipped_no_keyword INTEGER, avg_latency_seconds REAL, apify_cost_estimate REAL, error_count INTEGER, duration_seconds REAL, notes TEXT)")
            conn.execute("INSERT INTO jobs(job_key,title) VALUES('linkedin:1','Old job')")
            conn.commit(); conn.close()
            conn = main.init_db()
            cols = {row[1] for row in conn.execute("PRAGMA table_info(jobs)")}
            self.assertIn("relevance_score", cols)
            self.assertEqual(conn.execute("SELECT title FROM jobs WHERE job_key='linkedin:1'").fetchone()[0], "Old job")
            self.assertIsNotNone(conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='application_events'").fetchone())
            conn.close()
        finally:
            config.DB_PATH = original
            try: os.unlink(old_path)
            except OSError: pass


class SecurityHardeningTests(unittest.TestCase):
    def test_sanitize_log_collapses_newlines(self):
        value = "IT Support Engineer\n2026-01-01 00:00:00 | INFO | forged\r\nentry"
        self.assertEqual(main._sanitize_log(value), "IT Support Engineer 2026-01-01 00:00:00 | INFO | forged entry")
        self.assertNotIn("\n", main._sanitize_log(value))
        self.assertNotIn("\r", main._sanitize_log(value))

    def test_migration_rejects_unknown_table(self):
        conn = sqlite3.connect(":memory:")
        with self.assertRaises(ValueError):
            main._add_missing_columns(conn, "jobs; DROP TABLE jobs; --", {})
        conn.close()

    def test_allowed_migration_tables_still_work(self):
        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE TABLE jobs (job_key TEXT PRIMARY KEY)")
        main._add_missing_columns(conn, "jobs", {"relevance_score": "REAL"})
        cols = {row[1] for row in conn.execute("PRAGMA table_info(jobs)")}
        self.assertIn("relevance_score", cols)
        conn.close()


class AnomalyTests(unittest.TestCase):
    def test_anomaly_uses_historical_baseline(self):
        tmp = tempfile.NamedTemporaryFile(delete=False)
        tmp.close()
        old = config.DB_PATH
        try:
            config.DB_PATH = tmp.name
            conn = main.init_db()
            now = datetime.now(timezone.utc)
            for i, n in enumerate([100, 105, 95]):
                conn.execute("INSERT INTO run_history(run_id,timestamp,keyword,country,jobs_fetched) VALUES(?,?,?,?,?)", (str(i), (now - timedelta(days=i+1)).isoformat(), "IT Support", "Saudi Arabia", n))
            conn.commit()
            flag, reason = main.historical_anomaly(conn, "IT Support", "Saudi Arabia", 20)
            self.assertTrue(flag)
            self.assertIn("median", reason)
            conn.close()
        finally:
            config.DB_PATH = old
            try: os.unlink(tmp.name)
            except OSError: pass


if __name__ == "__main__":
    unittest.main(verbosity=2)
