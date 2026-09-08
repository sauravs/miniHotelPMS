# -*- coding: utf-8 -*-
"""
Slice 2 gate: no third-party personal data reaches the repository.

Decision D6. This repository is public and the captures came off MiniHotel's sandbox carrying
real-looking guest data. Two tests, because they answer different questions and only one of
them can run in CI.

The CI-safe one checks the COMMITTED fixtures against the pseudonym pools: every name that
appears is one we invented, every email ends in a reserved domain, every remark is redacted.
The local one, which skips when `raw/` is absent, does the real before-and-after comparison.
"""
import pathlib
import re

import pytest

from tools import scrub_fixtures as scrub

ROOT = pathlib.Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "fixtures" / "minihotel"
RAW = FIXTURES / "raw"

FIELDS = {
    "Email": r"<Email>([^<]*)</Email>",
    "Phone": r"<Phone>([^<]*)</Phone>",
    "Fax": r"<Fax>([^<]*)</Fax>",
    "IdNumber": r"<IdNumber>([^<]*)</IdNumber>",
    "givenName": r'givenName="([^"]*)"',
    "surname": r'surname="([^"]*)"',
    "NameOnCard": r'NameOnCard="([^"]*)"',
    "Street": r'Street="([^"]*)"',
    "City": r'City="([^"]*)"',
}


def committed():
    return sorted(FIXTURES.glob("*.xml"))


class TestCommittedFixturesCarryOnlyPseudonyms:
    """Runs everywhere, including CI, without needing the raw captures."""

    def test_there_are_fixtures_to_check(self):
        """A guard on the tests below: an empty glob would pass all of them vacuously."""
        assert len(committed()) == 14

    def test_every_name_is_one_we_invented(self):
        offenders = []
        for path in committed():
            text = path.read_text(encoding="utf-8")
            for value in re.findall(FIELDS["givenName"], text):
                if value.strip() and value not in scrub._GIVEN:
                    offenders.append("%s: givenName=%r" % (path.name, value))
            for value in re.findall(FIELDS["surname"], text):
                if value.strip() and value not in scrub._SURNAME:
                    offenders.append("%s: surname=%r" % (path.name, value))
        assert not offenders, offenders

    def test_every_email_uses_a_reserved_domain_that_cannot_route(self):
        """RFC 2606 reserves `.example` precisely so it can never reach anybody."""
        offenders = []
        for path in committed():
            for value in re.findall(FIELDS["Email"], path.read_text(encoding="utf-8")):
                if value.strip() and not value.endswith("@example.example"):
                    offenders.append("%s: %r" % (path.name, value))
        assert not offenders, offenders

    def test_every_free_text_remark_is_redacted(self):
        """The 2026 capture carried Hebrew prose naming a guest and recording that a manager
        approved an upgrade over Telegram - the sharpest finding in the project, and also
        personal data about a named individual."""
        offenders = []
        for path in committed():
            text = path.read_text(encoding="utf-8")
            for tag in ("PrintedRemarks", "NonPrintedRemarks", "SpecialRequest"):
                for value in re.findall(r"<%s[^>]*>([^<]*)</%s>" % (tag, tag), text):
                    if value.strip() and "redacted" not in value:
                        offenders.append("%s <%s>: %r" % (path.name, tag, value[:50]))
        assert not offenders, offenders

    def test_no_hebrew_text_survives(self):
        offenders = [p.name for p in committed()
                     if re.search(r"[֐-׿]", p.read_text(encoding="utf-8"))]
        assert not offenders, offenders

    def test_the_evidence_itself_is_untouched(self):
        """A scrubber that changed a balance, a status or a date would be rewriting the answer
        rather than protecting a person."""
        text = (FIXTURES / "5_balance_007004348.xml").read_text(encoding="utf-8")
        assert "-490.75" in text and "<Currency>ILS</Currency>" in text

    def test_every_fixture_is_indexed_with_the_request_that_produced_it(self):
        """Finding F19c. A fixture that does not know what it was asked cannot tell a caller
        when it is being asked something else."""
        import json
        index = json.loads((FIXTURES / "index.json").read_text(encoding="utf-8"))
        indexed = {entry["file"] for entry in index["responses"]}
        assert indexed == {p.name for p in committed()}
        for entry in index["responses"]:
            assert "request" in entry and "captured_at" in entry, entry["file"]


@pytest.mark.skipif(not RAW.is_dir(), reason="raw captures are git-ignored; local check only")
class TestAgainstTheRawCaptures:
    """The real proof, when the raw captures are present on this machine."""

    def test_every_populated_personal_value_actually_changed(self):
        unchanged = []
        for raw_path in sorted(RAW.glob("*.xml")):
            before = raw_path.read_text(encoding="utf-8")
            after = (FIXTURES / raw_path.name).read_text(encoding="utf-8")
            for field, pattern in FIELDS.items():
                for old, new in zip(re.findall(pattern, before), re.findall(pattern, after)):
                    if old.strip() and old == new:
                        unchanged.append("%s %s=%r" % (raw_path.name, field, old))
        assert not unchanged, unchanged

    def test_presence_is_preserved_exactly(self):
        """The property control 15 depends on: `reservation.guest.email exists` must give the
        same verdict before and after scrubbing, or the fixture answers a different question."""
        changed = []
        for raw_path in sorted(RAW.glob("*.xml")):
            before = raw_path.read_text(encoding="utf-8")
            after = (FIXTURES / raw_path.name).read_text(encoding="utf-8")
            for field, pattern in FIELDS.items():
                old_values, new_values = re.findall(pattern, before), re.findall(pattern, after)
                assert len(old_values) == len(new_values), "%s %s" % (raw_path.name, field)
                for old, new in zip(old_values, new_values):
                    if bool(old.strip()) != bool(new.strip()):
                        changed.append("%s %s: %r -> %r" % (raw_path.name, field, old, new))
        assert not changed, changed

    def test_rebuilding_the_fixtures_is_a_no_op(self):
        """Determinism, checked against what is actually committed. If this fails, every
        re-scrub is a spurious diff and no fixture assertion can be trusted to stay put."""
        for raw_path in sorted(RAW.glob("*.xml")):
            rebuilt = scrub.scrub_xml(raw_path.read_text(encoding="utf-8"))
            assert rebuilt == (FIXTURES / raw_path.name).read_text(encoding="utf-8"), \
                raw_path.name
