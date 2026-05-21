from __future__ import annotations

import json
from pathlib import Path

from .models import (
    AgentConfig,
    CitTimeRule,
    CrtTimeRule,
    PortalConfig,
    RegressionStatus,
    ScopeConfig,
    TimeRules,
)


DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "triage_config.json"


def load_config(path: str | Path = DEFAULT_CONFIG_PATH) -> AgentConfig:
    config_path = Path(path)
    data = json.loads(config_path.read_text(encoding="utf-8"))

    portal_data = data["portal"]
    time_data = data["time_rules"]

    return AgentConfig(
        portal=PortalConfig(
            base_url=portal_data["base_url"],
            org=portal_data["org"],
            limit=int(portal_data["limit"]),
            profile_dir=portal_data["profile_dir"],
            health_timeout_seconds=int(portal_data.get("health_timeout_seconds", 30)),
        ),
        time_rules=TimeRules(
            timezone=time_data["timezone"],
            cit=CitTimeRule(
                start_time=time_data["cit"]["start_time"],
                end_time=time_data["cit"]["end_time"],
            ),
            crt=CrtTimeRule(
                anchor_fb=time_data["crt"]["anchor_fb"],
                anchor_start_date=time_data["crt"]["anchor_start_date"],
                duration_days=int(time_data["crt"]["duration_days"]),
            ),
        ),
        scopes=[
            ScopeConfig(
                name=item["name"],
                regression_status=RegressionStatus(item["regression_status"]),
                testline=item["testline"],
            )
            for item in data["scopes"]
        ],
    )
