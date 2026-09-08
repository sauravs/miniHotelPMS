# -*- coding: utf-8 -*-
"""
Tenant configuration - one hotel's vocabulary, as data.

Resolves v1's open question 1.4, and fixes finding F12. In v1 the reservation-status map and
the folio-department map were dicts in a provider module, so onboarding a second property meant
editing Python. But those maps are not the provider's API surface: MiniHotel lets each property
customise its own status codes and posting categories (A5). The provider map describes an API;
the tenant config describes one hotel.

The other thing that lives here is everything a control needs that only the HOTEL can supply:
its timezone (F11), its call budget, the rate codes it has nominated for control 15, and the
rate-plan-to-room-type mapping MiniHotel cannot resolve (R13, open question 1.6).

The rule the whole file exists to protect: A CODE THAT IS NOT IN THE MAP RESOLVES TO UNKNOWN.
Never a guess. Across every capture, 44 of 217 distinct reservations - one in five - carry a
status code documented nowhere (`OK4`, `WL`). Silently mapping one of those would include or
exclude reservations from a control's scope invisibly.
"""
import pytest

from hotelcontrols.spec import SpecError, TenantConfig


@pytest.fixture(scope="module")
def tenant():
    return TenantConfig.load("sandbox")


class TestStatusVocabulary:
    def test_documented_codes_map_to_canonical_statuses(self, tenant):
        assert tenant.status("OUT") == "checked_out"
        assert tenant.status("IN") == "checked_in"
        assert tenant.status("CL") == "cancelled"
        assert tenant.status("OK") == "confirmed"

    def test_an_undocumented_code_is_unmapped_rather_than_guessed(self, tenant):
        """A5. `OK4` appears on 32 reservations and `WL` on 12, and neither is documented
        anywhere we have seen. A waitlist guess would be plausible and might be wrong, and a
        status decides whether a control applies at all."""
        assert tenant.status("OK4") is None
        assert tenant.status("WL") is None

    def test_the_unmapped_codes_are_declared_rather_than_merely_missing(self, tenant):
        """The difference between 'we have not got to it' and 'we have decided not to guess'.
        Declaring them is what lets the UI say how much of the property is unreadable."""
        assert set(tenant.known_unmapped_statuses) >= {"OK4", "WL"}

    def test_departments_ship_empty_because_they_are_per_property(self, tenant):
        """'RMS' is one property's posting category, not a provider-wide vocabulary. Every
        department is UNKNOWN until a hotel supplies its own mapping."""
        assert tenant.department("RMS") is None


class TestPropertySettings:
    def test_the_property_timezone_is_declared_and_real(self, tenant):
        """F11. This value decides which records a control even looks at."""
        assert tenant.timezone == "Asia/Jerusalem"
        assert tenant.clock().today() is not None

    def test_a_bogus_timezone_is_refused_at_load(self):
        with pytest.raises(SpecError):
            TenantConfig.from_dict({"tenant_id": "x", "provider": "minihotel",
                                    "timezone": "Middle/Earth"})

    def test_the_call_budget_is_a_property_level_decision(self, tenant):
        """R1/R8. How hard we are willing to lean on one hotel's PMS is that hotel's call."""
        assert tenant.call_budget >= 1

    def test_settings_a_control_needs_but_the_pms_cannot_supply(self, tenant):
        """Open questions 1.4 and 1.6, as configuration rather than as a placeholder string.

        v1's control 15 IR literally contained `["<hotel-nominated rate codes>"]` - a
        placeholder sitting in a rule that was otherwise executable.
        """
        assert tenant.setting("nominated_rate_codes") == []
        assert tenant.setting("rate_plan_permitted_room_types") == {}

    def test_an_undeclared_setting_is_an_error_not_an_empty_default(self, tenant):
        """An IR naming a setting nobody defined must be caught by the validator, not
        silently evaluate against an empty list and exclude every record."""
        with pytest.raises(SpecError):
            tenant.setting("nominated_unicorns")

    def test_a_tenant_config_is_immutable(self, tenant):
        with pytest.raises((AttributeError, TypeError)):
            tenant.timezone = "UTC"
