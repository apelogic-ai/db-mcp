"""discover_structure must route catalog/schema calls through the adapter layer.

These tests were superseded by test_discover_structure_via_gateway.py once
discover_structure was updated to accept connection_path and call
gateway.introspect() directly. Kept as stubs to avoid import errors in CI.
"""


def test_discover_structure_routes_through_gateway():
    """Superseded — see test_discover_structure_via_gateway.py."""
    pass


def test_discover_structure_gateway_passes_catalog():
    """Superseded — see test_discover_structure_via_gateway.py."""
    pass
