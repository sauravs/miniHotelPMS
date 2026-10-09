# -*- coding: utf-8 -*-
"""
Slice 19's two locks, asserted NEGATIVELY: no test can send an email (criterion V6).

The SMTP backend lives in `tools/notifiers/`, outside the engine, and is injected by
`tools/serve.py` - exactly as `tools/proposers/` is (D10). It refuses to connect unless
`HOTELCONTROLS_NOTIFY=1` is set AND no test runner is loaded. An environment variable alone is
a lock a test opens in one line (`monkeypatch.setenv`), so there are two, and the test that
opens the first is refused by the second. That is what these tests do.

`smtplib` is standard library, so `test_stdlib_only.py` would not notice it in the engine. The
plan requires that test, and the transport's lock tests, to pass UNEDITED - so the stronger
rule is asserted here, in a new file: nothing under `hotelcontrols/` imports `smtplib`, or this
package, at all.
"""
import ast
import pathlib

import pytest

from hotelcontrols.actions import Message, NotifyFailed
from tools import notifiers
from tools.notifiers import NotifierDisabled, RecordingNotifier
from tools.notifiers.smtp import SmtpNotifier

ROOT = pathlib.Path(__file__).resolve().parents[2]
ENGINE = ROOT / "hotelcontrols"

MESSAGE = Message(action_id="a1", tenant_id="sandbox", audience="finance",
                  to=("finance@example.test",), subject="s", body="b")


@pytest.fixture
def no_connection(monkeypatch):
    """Any attempt to open an SMTP connection is recorded and refused. If a lock ever fails
    open, the test fails on THIS list, not on a timeout against somebody's mail server."""
    attempts = []

    def refuse(*args, **kwargs):
        attempts.append((args, kwargs))
        raise AssertionError("a test reached smtplib.SMTP - a lock failed open")

    monkeypatch.setattr("smtplib.SMTP", refuse)
    return attempts


def smtp():
    return SmtpNotifier(host="mail.example.test", port=587, sender="controls@example.test")


class TestTheTwoLocks:

    def test_lock_1_without_the_variable_it_refuses(self, monkeypatch, no_connection):
        monkeypatch.delenv("HOTELCONTROLS_NOTIFY", raising=False)
        with pytest.raises(NotifierDisabled, match="HOTELCONTROLS_NOTIFY"):
            smtp().send(MESSAGE)
        assert no_connection == []

    def test_lock_2_with_the_variable_set_inside_pytest_it_still_refuses(self, monkeypatch,
                                                                         no_connection):
        """Exit test 3, by name: HOTELCONTROLS_NOTIFY=1 set inside pytest, and refused."""
        monkeypatch.setenv("HOTELCONTROLS_NOTIFY", "1")
        with pytest.raises(NotifierDisabled, match="test process"):
            smtp().send(MESSAGE)
        assert no_connection == []

    def test_a_refusal_is_a_named_delivery_failure_not_a_crash(self):
        """So dispatch leaves the task unsent with the reason, rather than raising out of a
        run page."""
        assert issubclass(NotifierDisabled, NotifyFailed)


class TestRoutesComeFromTheEnvironmentWithNoDefault:
    """Staff addresses are personal data: environment only, never committed, no default."""

    def test_an_audience_with_no_variable_has_no_route(self, monkeypatch):
        monkeypatch.delenv("HOTELCONTROLS_NOTIFY_FINANCE", raising=False)
        assert notifiers.routes_from_environment("finance") == ()
        assert smtp().route("finance") == ()

    def test_a_route_is_a_comma_separated_list_and_blanks_are_dropped(self, monkeypatch):
        monkeypatch.setenv("HOTELCONTROLS_NOTIFY_FINANCE", " a@example.test, ,b@example.test ")
        assert smtp().route("finance") == ("a@example.test", "b@example.test")

    def test_the_variable_name_is_derived_from_the_audience(self):
        assert notifiers.route_variable("front_office_manager") == \
            "HOTELCONTROLS_NOTIFY_FRONT_OFFICE_MANAGER"
        assert notifiers.route_variable("revenue-manager") == \
            "HOTELCONTROLS_NOTIFY_REVENUE_MANAGER"

    def test_the_backend_needs_its_server_and_sender_from_the_environment(self, monkeypatch):
        """No default host and no default sender, so a missing one fails loudly at startup
        rather than mailing from somewhere nobody chose."""
        for name in ("HOTELCONTROLS_SMTP_HOST", "HOTELCONTROLS_SMTP_FROM"):
            monkeypatch.delenv(name, raising=False)
        with pytest.raises(RuntimeError, match="HOTELCONTROLS_SMTP_HOST"):
            SmtpNotifier.from_environment()
        monkeypatch.setenv("HOTELCONTROLS_SMTP_HOST", "mail.example.test")
        with pytest.raises(RuntimeError, match="HOTELCONTROLS_SMTP_FROM"):
            SmtpNotifier.from_environment()
        monkeypatch.setenv("HOTELCONTROLS_SMTP_FROM", "controls@example.test")
        built = SmtpNotifier.from_environment()
        assert (built.host, built.sender) == ("mail.example.test", "controls@example.test")

    def test_a_user_without_a_password_is_refused(self, monkeypatch):
        monkeypatch.setenv("HOTELCONTROLS_SMTP_HOST", "mail.example.test")
        monkeypatch.setenv("HOTELCONTROLS_SMTP_FROM", "controls@example.test")
        monkeypatch.setenv("HOTELCONTROLS_SMTP_USER", "someone")
        monkeypatch.delenv("HOTELCONTROLS_SMTP_PASSWORD", raising=False)
        with pytest.raises(RuntimeError, match="HOTELCONTROLS_SMTP_PASSWORD"):
            SmtpNotifier.from_environment()


class TestTheChooser:

    def test_off_is_none_and_is_the_default(self):
        assert notifiers.DEFAULT == "off"
        assert notifiers.build("off") is None

    def test_an_unknown_backend_is_refused_by_name(self):
        with pytest.raises(ValueError, match="no notifier called"):
            notifiers.build("carrier-pigeon")

    def test_the_recording_stub_needs_nothing_and_sends_nothing(self):
        stub = RecordingNotifier({"finance": ("f@example.test",)})
        stub.send(MESSAGE)
        assert stub.sent == [MESSAGE] and stub.route("nobody") == ()


class TestTheEngineCannotReachIt:

    def _imports(self, path):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                yield from (alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                yield node.module

    def test_no_engine_module_imports_smtplib_or_a_notifier_backend(self):
        offenders = ["%s imports %s" % (path.relative_to(ROOT), name)
                     for path in sorted(ENGINE.rglob("*.py"))
                     for name in self._imports(path)
                     if name.split(".")[0] in ("smtplib", "email", "tools")]
        assert not offenders, offenders

    def test_exactly_one_file_in_tools_notifiers_imports_smtplib(self):
        found = [path.name for path in sorted((ROOT / "tools" / "notifiers").glob("*.py"))
                 if "smtplib" in set(self._imports(path))]
        assert found == ["smtp.py"]


class TestWhatTheBackendWouldSay:
    """The send path past the locks, against a FAKE `smtplib.SMTP`. The locks are bypassed by
    patching `assert_armed` in this module only, and the fake records calls - nothing can leave
    the process. What is under test is the conversation: verified STARTTLS first, a login only
    when a user is configured, and the message's addresses and words as rendered."""

    class FakeSMTP:
        calls: list = []

        def __init__(self, host, port, timeout):
            self.calls.append(("connect", host, port))

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def starttls(self, context=None):
            import ssl
            assert isinstance(context, ssl.SSLContext)
            assert context.verify_mode == ssl.CERT_REQUIRED and context.check_hostname
            self.calls.append(("starttls",))

        def login(self, user, password):
            self.calls.append(("login", user))

        def send_message(self, email):
            self.calls.append(("send", email["From"], email["To"], email["Subject"],
                               email.get_content()))

    @pytest.fixture
    def fake(self, monkeypatch):
        self.FakeSMTP.calls = []
        monkeypatch.setattr("tools.notifiers.smtp.assert_armed", lambda what: None)
        monkeypatch.setattr("smtplib.SMTP", self.FakeSMTP)
        return self.FakeSMTP.calls

    def test_verified_starttls_then_the_message_and_no_login_without_a_user(self, fake):
        smtp().send(MESSAGE)
        assert fake == [("connect", "mail.example.test", 587), ("starttls",),
                        ("send", "controls@example.test", "finance@example.test", "s", "b\n")]

    def test_a_configured_user_logs_in_after_starttls(self, fake):
        SmtpNotifier(host="mail.example.test", port=587, sender="controls@example.test",
                     user="someone", password="from-the-environment").send(MESSAGE)
        assert [call[0] for call in fake] == ["connect", "starttls", "login", "send"]

    def test_a_server_refusal_is_a_named_delivery_failure(self, monkeypatch):
        import smtplib

        def refuse(*args, **kwargs):
            raise smtplib.SMTPConnectError(421, b"try later")

        monkeypatch.setattr("tools.notifiers.smtp.assert_armed", lambda what: None)
        monkeypatch.setattr("smtplib.SMTP", refuse)
        with pytest.raises(NotifyFailed, match="SMTPConnectError"):
            smtp().send(MESSAGE)
