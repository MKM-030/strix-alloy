"""Apply the unchanged managed serving contract to the newly pinned release."""
try:
    from . import test_halogen0202_forwarding as baseline
except ImportError:
    import test_halogen0202_forwarding as baseline


class Halogen0203Forwarding(baseline.Halogen0202Forwarding):
    version = '0.20.3'
