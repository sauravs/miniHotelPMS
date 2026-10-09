# -*- coding: utf-8 -*-
"""
Slice 20 (G14, narrowed): the operational log's own rules, before any run is involved.

Structured JSON-lines records through the standard `logging` module. What this pins:

  - every record carries `tenant_id`, `run_id`, `control_id`, `policy_version` and `provider`,
    null where a boundary has none - so a reader can always filter on the same five keys;
  - THE TIMESTAMP IS THE INJECTED CLOCK'S. A `LogRecord` reads the machine's wall clock when it
    is made, and `kernel/clock.py` is the only module allowed to (F11). So the line written is
    the record we built, stamped by our clock, and never the `LogRecord`'s `created` or
    `asctime`;
  - `evaluator/` imports no logging (purity is load-bearing there), and nothing inside
    `providers/` logs at all - anything logged in an adapter would name endpoints above the
    canonical boundary.
"""
import ast
import io
import json
import logging
import pathlib
from datetime import datetime, timedelta, timezone

import pytest

from hotelcontrols.kernel import FixedClock
from hotelcontrols.ops import CARRIES, JsonLines, OpsLog, attach, elapsed_ms

ENGINE = pathlib.Path(__file__).resolve().parents[2] / "hotelcontrols"
INSTANT = datetime(2026, 10, 9, 6, 30, tzinfo=timezone.utc)


class Capture(logging.Handler):
    """Every record a logger handles, and every line the formatter would write for it."""

    def __init__(self):
        super().__init__()
        self.records, self.lines = [], []
        self.setFormatter(JsonLines())

    def emit(self, record):
        self.records.append(record)
        self.lines.append(self.format(record))


@pytest.fixture
def captured(request):
    logger = logging.getLogger("test.ops.%s" % request.node.name)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    handler = Capture()
    logger.addHandler(handler)
    yield logger, handler
    logger.removeHandler(handler)


class TestARecord:

    def test_carries_the_five_keys_even_when_a_boundary_has_none(self, captured):
        logger, handler = captured
        OpsLog(clock=FixedClock(INSTANT), logger=logger).emit("request", path="/", status=200)
        (line,) = handler.lines
        record = json.loads(line)
        assert CARRIES == ("tenant_id", "run_id", "control_id", "policy_version", "provider")
        assert [key for key in record][:7] == ["at", "event", *CARRIES]
        assert all(record[key] is None for key in CARRIES)
        assert (record["event"], record["path"], record["status"]) == ("request", "/", 200)

    def test_is_stamped_by_the_injected_clock_not_the_log_records_own(self, captured):
        """A LogRecord made now reads 2026-10-09 by the machine's clock. The line says what the
        injected clock says - here a fixed instant years from any machine's idea of now."""
        logger, handler = captured
        fixed = datetime(2031, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
        OpsLog(clock=FixedClock(fixed), logger=logger).emit("run", run_id="r1")
        record = json.loads(handler.lines[0])
        assert record["at"] == "2031-01-02T03:04:05+00:00"
        assert set(record) == {"at", "event", *CARRIES}       # no asctime, no created, no level

    def test_the_line_is_the_record_and_nothing_else(self, captured):
        logger, handler = captured
        built = OpsLog(clock=FixedClock(INSTANT), logger=logger).emit(
            "dispatch", tenant_id="sandbox", outcome="sent")
        assert json.loads(handler.lines[0]) == built

    def test_a_foreign_record_on_the_same_logger_still_writes_no_wall_clock(self):
        """Something else logging to this logger gets its message, never a timestamp."""
        record = logging.LogRecord("x", logging.INFO, __file__, 1, "hello", None, None)
        assert json.loads(JsonLines().format(record)) == {"event": "hello"}

    def test_a_default_log_uses_the_kernels_clock_in_utc(self):
        """No clock handed in: the kernel's production clock, in UTC - an operational log is
        about the service, not about one hotel's calendar."""
        log = OpsLog()
        assert log.now().utcoffset() == timedelta(0)


class TestDuration:

    def test_elapsed_is_whole_milliseconds_between_two_instants_of_the_injected_clock(self):
        assert elapsed_ms(INSTANT, INSTANT + timedelta(seconds=1.2345)) == 1235
        assert elapsed_ms(INSTANT, INSTANT) == 0


class TestAttaching:

    def test_attach_writes_json_lines_to_a_stream(self):
        stream = io.StringIO()
        handler = attach(stream)
        try:
            OpsLog(clock=FixedClock(INSTANT)).emit("request", status=200)
        finally:
            logging.getLogger("hotelcontrols.ops").removeHandler(handler)
        (line,) = stream.getvalue().splitlines()
        assert json.loads(line)["status"] == 200

    def test_the_ops_logger_does_not_propagate_into_somebody_elses_root_handlers(self):
        handler = attach(io.StringIO())
        try:
            assert logging.getLogger("hotelcontrols.ops").propagate is False
        finally:
            logging.getLogger("hotelcontrols.ops").removeHandler(handler)


class TestWhereLoggingMayNotAppear:
    """plan-v3 §5 slice 20: 'purity is asserted; no logging import may appear' in evaluator/,
    and nothing logged inside providers/ (an adapter would name endpoints above the boundary)."""

    @staticmethod
    def imports(path):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                yield from (alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                yield node.module.split(".")[0] if node.level == 0 else ""
                if node.level and node.module.split(".")[-1] == "ops":
                    yield "ops"

    @pytest.mark.parametrize("package", ["evaluator", "providers"])
    def test_imports_no_logging_and_not_the_ops_log(self, package):
        files = sorted((ENGINE / package).rglob("*.py"))
        assert files, "nothing to check - the test would pass vacuously"
        offenders = ["%s imports %s" % (p.relative_to(ENGINE), name)
                     for p in files for name in self.imports(p) if name in ("logging", "ops")]
        assert not offenders, offenders

    def test_the_guard_sees_a_planted_import(self, tmp_path):
        planted = tmp_path / "record.py"
        planted.write_text("import logging\nfrom ..ops import OpsLog\n", encoding="utf-8")
        assert set(self.imports(planted)) >= {"logging", "ops"}
