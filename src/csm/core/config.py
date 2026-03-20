"""User configuration file support (~/.csm/config.json)."""
import json
import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_CONFIG_PATH = Path.home() / ".csm" / "config.json"


@dataclass
class UserConfig:
    """User preferences loaded from config file."""
    default_model: str | None = None
    default_permission_mode: str = "auto"
    default_max_budget_usd: float | None = None
    auto_compact_threshold: int = 50000
    session_limit: int = 20
    output_buffer_capacity: int = 1000
    refresh_interval: float = 1.0
    auto_restart_dead: bool = False
    auto_restart_max: int = 3


def load_config(path: Path = DEFAULT_CONFIG_PATH) -> UserConfig:
    """Load user config from JSON file. Returns defaults if not found."""
    path = Path(path)
    if not path.exists():
        return UserConfig()
    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
        return UserConfig(
            default_model=data.get("default_model"),
            default_permission_mode=data.get("default_permission_mode", "auto"),
            default_max_budget_usd=data.get("default_max_budget_usd"),
            auto_compact_threshold=max(1000, data.get("auto_compact_threshold", 50000)),
            session_limit=max(1, data.get("session_limit", 20)),
            output_buffer_capacity=max(100, data.get("output_buffer_capacity", 1000)),
            refresh_interval=max(0.5, data.get("refresh_interval", 1.0)),
            auto_restart_dead=data.get("auto_restart_dead", False),
            auto_restart_max=max(0, data.get("auto_restart_max", 3)),
        )
    except (json.JSONDecodeError, ValueError) as e:
        logger.warning("Failed to load config from %s: %s", path, e)
        return UserConfig()


def save_default_config(path: Path = DEFAULT_CONFIG_PATH) -> None:
    """Write a default config file with comments."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    default = {
        "default_model": None,
        "default_permission_mode": "auto",
        "default_max_budget_usd": None,
        "auto_compact_threshold": 50000,
        "session_limit": 20,
        "output_buffer_capacity": 1000,
        "refresh_interval": 1.0,
        "auto_restart_dead": False,
        "auto_restart_max": 3,
    }
    path.write_text(json.dumps(default, indent=2), encoding="utf-8")
    logger.info("Wrote default config to %s", path)
