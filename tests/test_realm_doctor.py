import os
import shutil
import ssl
import subprocess
import unittest
from datetime import timedelta
from pathlib import Path
from unittest import mock

from guild import paths, timeutil
from guild.commands import doctor as doctor_commands
from guild.commands import realm as realm_commands
from guild.realm import checks, clientconfig, hubconfig, pin
from tests import realm_hub_fixture
from tests.testutil import GuildTestCase


@unittest.skipUnless(shutil.which("openssl"), "openssl not on PATH")
class RealmDoctorTests(GuildTestCase):
    def setUp(self):
        super().setUp()
        patcher = mock.patch.dict(os.environ)
        patcher.start()
        self.addCleanup(patcher.stop)
        os.environ.pop("CLAUDECODE", None)
        self.server, self.cert, self.tokens = realm_hub_fixture.start_hub(self)
        self.url = "https://127.0.0.1:{}".format(self.server.server_address[1])
        self.fingerprint = pin.cert_fingerprint(self.cert)
        self.now = timeutil.utcnow()

    def _join(self, member):
        paths.global_config_path().parent.mkdir(parents=True, exist_ok=True)
        paths.global_config_path().write_text('{{"name": "{}"}}'.format(member))
        argv = ["realm", "join", self.url, "--fingerprint", self.fingerprint]
        with mock.patch("getpass.getpass", return_value=self.tokens[member]):
            self.assertEqual(self.run_cli(argv, None, self.root)[0], 0)

    def _push(self):
        self.assertEqual(self.run_cli(["realm", "push"], None, self.root)[0], 0)

    def _rewrite_join(self, **changes):
        clientconfig.save(dict(clientconfig.load(), **changes))

    def _guild(self, now=None):
        return checks.guild_lines(self.now if now is None else now)

    def _texts(self, lines):
        return [text for _, text in lines]

    def _failures(self, lines):
        return [text for passed, text in lines if not passed]

    def _warnings(self, lines):
        return [text for passed, text in lines if passed and text.startswith("warn")]

    def _assert_stops_after(self, lines, failure):
        self.assertEqual(len(self._failures(lines)), 1, lines)
        self.assertIn(failure, lines[-1][1])
        self.assertFalse(lines[-1][0])

    def test_no_realm_joined_is_one_ok_line(self):
        self.assertEqual(self._guild(), [(True, "ok      no realm joined")])

    def test_healthy_guild_passes_every_check(self):
        self._join("alpha")
        self._push()
        lines = self._guild()
        self.assertTrue(all(passed for passed, _ in lines), lines)
        self.assertEqual(self._warnings(lines), [])
        joined = "\n".join(self._texts(lines))
        for expected in ("realm config", "pinned fingerprint", "token accepted", "member matches", "realm matches test-realm", "clock agrees", "last push"):
            self.assertIn(expected, joined)

    def test_open_config_mode_fails(self):
        self._join("alpha")
        paths.realm_config_path().chmod(0o644)
        lines = self._guild()
        self.assertIn("mode must be 0600", self._failures(lines)[0])
        self.assertEqual(len(lines), 2)

    def test_bad_config_shape_stops_the_checks(self):
        self._join("alpha")
        paths.realm_config_path().write_text("{}")
        paths.realm_config_path().chmod(0o600)
        lines = self._guild()
        self.assertEqual(len(lines), 1)
        self.assertFalse(lines[0][0])

    def test_hub_down_fails_once(self):
        self._join("alpha")
        self._rewrite_join(url="https://127.0.0.1:1")
        self._assert_stops_after(self._guild(), "realm hub unreachable")

    def test_wrong_fingerprint_fails_once(self):
        self._join("alpha")
        self._rewrite_join(fingerprint="AA:" * 31 + "AA")
        self._assert_stops_after(self._guild(), "fingerprint mismatch")

    def test_tls12_server_fails_once(self):
        self._join("alpha")
        hub_config = hubconfig.load()
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.maximum_version = ssl.TLSVersion.TLSv1_2
        context.load_cert_chain(hub_config["cert"], hub_config["key"])
        url = realm_hub_fixture.serve_once(self, lambda peer: context.wrap_socket(peer, server_side=True))
        self._rewrite_join(url=url)
        self._assert_stops_after(self._guild(), "TLS 1.3 handshake")

    def test_revoked_token_fails_and_stops(self):
        self._join("alpha")
        realm_commands.member_remove("alpha", None)
        lines = self._guild()
        self.assertEqual(len(self._failures(lines)), 1)
        self.assertIn("token not accepted: realm hub refused (401)", self._failures(lines)[0])
        self.assertFalse(any("last push" in text or "never pushed" in text for text in self._texts(lines)))

    def test_member_mismatch_fails(self):
        self._join("alpha")
        self._rewrite_join(token=self.tokens["beta"])
        failures = self._failures(self._guild())
        self.assertEqual(failures, ["fail    token belongs to beta, this guild is alpha"])

    def test_renamed_realm_fails(self):
        self._join("alpha")
        hub_config = hubconfig.load()
        hub_config["name"] = "renamed"
        hubconfig.save(hub_config)
        failures = self._failures(self._guild())
        self.assertEqual(failures, ["fail    hub calls its realm renamed, this guild joined test-realm"])

    def test_never_pushed_warns(self):
        self._join("alpha")
        lines = self._guild()
        self.assertEqual(self._warnings(lines), ["warn    this guild never pushed"])
        self.assertEqual(self._failures(lines), [])

    def test_stale_push_warns_with_age(self):
        self._join("alpha")
        self._push()
        warnings = self._warnings(self._guild(self.now + timedelta(minutes=20)))
        self.assertRegex(warnings[-1], r"last push (19|20)m ago: is the push timer running\?")

    def test_clock_skew_warns(self):
        self._join("alpha")
        self._push()
        warnings = self._warnings(self._guild(self.now + timedelta(minutes=10)))
        self.assertEqual(len(warnings), 1)
        self.assertIn("clock differs from the hub by", warnings[0])

    def test_missing_or_unreadable_date_header_warns(self):
        self._join("alpha")
        self._push()
        for header in (None, "not a date"):
            lines = checks._skew_lines(header, self.now)
            self.assertEqual(len(lines), 1)
            self.assertTrue(lines[0][0])
            self.assertTrue(lines[0][1].startswith("warn"))

    def test_invalid_received_at_fails(self):
        self._join("alpha")
        entry = {"guild": "alpha", "received_at": "garbage"}
        with mock.patch.object(checks.client, "exchange", return_value=(200, {"guilds": [entry]}, None)):
            lines = checks._push_lines(clientconfig.load(), self.now)
        self.assertEqual(lines, [(False, "fail    hub sent an invalid status")])

    def test_status_read_failures_are_reported(self):
        self._join("alpha")
        config = clientconfig.load()
        with mock.patch.object(checks.client, "exchange", return_value=(500, {"error": "boom"}, None)):
            self.assertIn("could not read status: realm hub refused (500): boom", checks._push_lines(config, self.now)[0][1])
        with mock.patch.object(checks.client, "exchange", side_effect=checks.GuildError("realm hub request failed: URLError", 1)):
            self.assertEqual(checks._push_lines(config, self.now), [(False, "fail    realm hub request failed: URLError")])

    def _hub(self, now=None):
        return checks.hub_lines(self.now if now is None else now)

    def _mode_failures(self):
        return "\n".join(self._failures(self._hub()))

    def test_no_hub_config_gives_no_hub_lines(self):
        paths.realm_hub_config_path().unlink()
        self.assertEqual(self._hub(), [])

    def test_healthy_hub_has_no_failures(self):
        lines = self._hub()
        self.assertEqual(self._failures(lines), [])
        self.assertIn("hub certificate valid until", "\n".join(self._texts(lines)))
        self.assertEqual(self._warnings(lines).count("warn    member alpha never pushed"), 1)

    def test_bad_modes_fail(self):
        key = hubconfig.load()["key"]
        for path in (paths.realm_hub_config_path(), key):
            os.chmod(path, 0o644)
        for path in (paths.realm_hub_pki_dir(), paths.realm_hub_store_dir(), paths.realm_hub_store_dir() / "status"):
            os.chmod(path, 0o755)
        failures = self._mode_failures()
        for label in ("hub config", "hub key", "hub pki dir", "hub store dir"):
            self.assertIn(label, failures)
        self.assertEqual(failures.count("hub store dir"), 2)

    def test_missing_key_fails(self):
        os.unlink(hubconfig.load()["key"])
        self.assertIn("hub key missing", self._mode_failures())

    def test_malformed_hub_config_fails(self):
        paths.realm_hub_config_path().write_text("{}")
        paths.realm_hub_config_path().chmod(0o600)
        lines = self._hub()
        self.assertFalse(lines[-1][0])
        self.assertIn("malformed", lines[-1][1])

    def test_certificate_near_expiry_warns(self):
        cert = hubconfig.load()["cert"]
        subprocess.run(
            [
                "openssl", "req", "-x509", "-newkey", "ec", "-pkeyopt", "ec_paramgen_curve:prime256v1",
                "-nodes", "-days", "10", "-subj", "/CN=guild-realm", "-keyout", os.devnull, "-out", cert,
            ],
            check=True, capture_output=True,
        )
        warnings = self._warnings(self._hub())
        self.assertEqual(len([w for w in warnings if "hub certificate expires in" in w]), 1)
        self.assertEqual(self._failures(self._hub()), [])

    def test_expired_certificate_fails(self):
        end = self.now - timedelta(days=1)
        with mock.patch.object(checks, "_cert_end", return_value=end):
            self.assertIn("hub certificate expired", self._mode_failures())

    def test_missing_openssl_warns(self):
        with mock.patch.object(checks.shutil, "which", return_value=None):
            lines = self._hub()
        self.assertIn("warn    openssl not found on PATH: certificate expiry not checked", self._texts(lines))
        self.assertEqual(self._failures(lines), [])

    def test_unreadable_certificate_fails(self):
        hub_config = hubconfig.load()
        Path(hub_config["cert"]).write_text("junk")
        self.assertIn("openssl could not read the hub certificate", self._mode_failures())

    def test_unparsable_end_date_fails(self):
        fake = subprocess.CompletedProcess([], 0, stdout="notAfter=whenever\n", stderr="")
        with mock.patch.object(checks.subprocess, "run", return_value=fake):
            self.assertIn("unreadable certificate end date", self._mode_failures())

    def test_member_states(self):
        self._join("alpha")
        self._push()
        fresh = self._hub()
        self.assertIn("ok      member alpha pushed 0s ago", self._texts(fresh))
        self.assertIn("warn    member beta never pushed", self._texts(fresh))
        stale = self._texts(self._hub(self.now + timedelta(hours=3)))
        self.assertIn("warn    member alpha last pushed 2h ago", stale)

    def test_unreadable_member_status_warns(self):
        (paths.realm_hub_store_dir() / "status" / "alpha.json").write_text("{nope")
        self.assertIn("warn    member alpha has an unreadable status file", self._texts(self._hub()))

    def test_all_lines_joins_both_sides(self):
        self._join("alpha")
        joined = "\n".join(self._texts(checks.all_lines(self.now)))
        self.assertIn("token accepted", joined)
        self.assertIn("hub certificate", joined)

    def test_cli_prints_lines_and_exit_follows_failures(self):
        self._join("alpha")
        code, out, err = self.run_cli(["realm", "doctor"], None, self.root)
        self.assertEqual(code, 0, err)
        self.assertIn("ok      token accepted", out)
        self.assertIn("warn    this guild never pushed", out)
        self._rewrite_join(url="https://127.0.0.1:1")
        code, out, err = self.run_cli(["realm", "doctor"], None, self.root)
        self.assertEqual(code, 1)
        self.assertIn("fail    realm hub unreachable", out)

    def test_cli_runs_inside_a_claude_session(self):
        os.environ["CLAUDECODE"] = "1"
        self.assertEqual(self.run_cli(["realm", "doctor"], None, self.root)[0], 0)

    def test_guild_doctor_still_reports_the_realm_config(self):
        self._join("alpha")
        self.assertEqual(checks.config_lines(), [(True, "ok      realm config")])
        self.assertIs(doctor_commands.realm_checks, checks)


if __name__ == "__main__":
    unittest.main()
