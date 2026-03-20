"""Session templates - save/load reusable session configurations."""
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_TEMPLATES_PATH = Path.home() / ".csm" / "templates.json"


def save_template(
    name: str,
    config: dict,
    path: Path = DEFAULT_TEMPLATES_PATH,
) -> None:
    """Save a session config as a named template."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    templates = load_templates(path)
    templates[name] = config
    path.write_text(json.dumps(templates, indent=2, ensure_ascii=False), encoding="utf-8")


def load_templates(
    path: Path = DEFAULT_TEMPLATES_PATH,
) -> dict[str, dict]:
    """Load all templates. Returns empty dict if not found."""
    path = Path(path)
    if not path.exists():
        return {}
    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, ValueError):
        return {}


def delete_template(
    name: str,
    path: Path = DEFAULT_TEMPLATES_PATH,
) -> bool:
    """Delete a template by name. Returns True if found and deleted."""
    path = Path(path)
    templates = load_templates(path)
    if name not in templates:
        return False
    del templates[name]
    path.write_text(json.dumps(templates, indent=2, ensure_ascii=False), encoding="utf-8")
    return True


def list_template_names(
    path: Path = DEFAULT_TEMPLATES_PATH,
) -> list[str]:
    """List all template names."""
    return list(load_templates(path).keys())
