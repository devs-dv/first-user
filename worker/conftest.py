"""pytest entry point: the same guard as test_support (see there). unittest runs import test_support directly."""

import test_support  # noqa: F401  (must come first: it keeps tests from sending traces to neatlogs)
