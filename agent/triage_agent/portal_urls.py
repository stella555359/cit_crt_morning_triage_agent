from __future__ import annotations

from urllib.parse import urlencode

from .models import PortalConfig, ScopeConfig


def build_test_runs_url(portal: PortalConfig, scope: ScopeConfig) -> str:
    params = {
        "limit": str(portal.limit),
        "org": portal.org,
        "regression_status": scope.regression_status.value,
        "test_line": scope.testline,
    }
    return f"{portal.base_url}?{urlencode(params)}"
