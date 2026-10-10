# -*- coding: utf-8 -*-
"""
`.env.example` names the variables the code actually reads - issue #80.

Slice 24 (#22) moved credentials to `HOTELCONTROLS_<PROPERTY>_<PROVIDER>_*` with no fallback, and
the example kept the provider-only names: copied and filled in, it produced a `MissingCredential`
for a variable it never mentioned. An example that disagrees with the code is worse than none,
so the names are derived here from the same places the code derives them.
"""
import pathlib
import re

from hotelcontrols.spec import TenantConfig, available_tenants
from hotelcontrols.web import auth

ROOT = pathlib.Path(__file__).resolve().parents[2]
EXAMPLE = (ROOT / ".env.example").read_text(encoding="utf-8")
KEYS = set(re.findall(r"^([A-Z][A-Z0-9_]*)=", EXAMPLE, re.M))
FIELDS = ("BASE_URL", "USER", "PASSWORD", "HOTEL")


def test_every_live_property_has_its_four_credential_names():
    """Only properties whose provider can be probed live have credentials at all."""
    from hotelcontrols.providers import registry
    live = [t for t in map(TenantConfig.load, available_tenants())
            if registry.load(t.provider).encoder is not None]
    assert live, "a guard: no live property would make this test vacuous"
    for tenant in live:
        for field in FIELDS:
            name = "HOTELCONTROLS_%s_%s_%s" % (tenant.tenant_id.upper(),
                                               tenant.provider.upper(), field)
            assert name in KEYS, name


def test_no_provider_only_credential_name_survives():
    """The engine never reads them (no fallback, #22), so the example must not offer them."""
    stale = sorted(k for k in KEYS if re.fullmatch(r"HOTELCONTROLS_MINIHOTEL_(%s)" % "|".join(FIELDS), k))
    assert stale == []


def test_the_authentication_variables_are_documented_with_no_value():
    """Named, explained, and empty: a secret in a committed example is a secret. The secret and
    the dev users ship COMMENTED OUT - sourced as an empty variable, the secret would make the
    engine refuse to start, which is right for a real misconfiguration and wrong for a copy of
    the example."""
    assert auth.DEMAND_VARIABLE in KEYS
    for name in (auth.SECRET_VARIABLE, "HOTELCONTROLS_UI_DEV_USERS"):
        assert name not in KEYS, "%s must not be set by the example" % name
        assert re.search(r"^#\s*%s=\s*$" % name, EXAMPLE, re.M), name
