"""YAML configuration file loader."""

from pathlib import Path
from typing import Any, Dict

import yaml


def load_yaml_config(config_path: str | Path) -> Dict[str, Any]:
    """Load a YAML configuration file.

    Args:
        config_path: Path to YAML config file

    Returns:
        Dictionary containing parsed YAML content

    Raises:
        FileNotFoundError: If config file does not exist
        yaml.YAMLError: If YAML parsing fails
    """
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_source_config(
    source_type: str,
    base_dir: str = "config/sources"
) -> Dict[str, Any]:
    """Load source-specific configuration YAML.

    Args:
        source_type: Type of source (e.g., 'twitter', 'reddit')
        base_dir: Base directory containing source configs

    Returns:
        Dictionary containing source configuration
    """
    return load_yaml_config(Path(base_dir) / f"{source_type}.yaml")


def load_persona_config(
    persona_name: str = "default",
    base_dir: str = "config/personas"
) -> Dict[str, Any]:
    """Load persona configuration YAML.

    Args:
        persona_name: Name of persona (e.g., 'default', 'technical')
        base_dir: Base directory containing persona configs

    Returns:
        Dictionary containing persona configuration
    """
    return load_yaml_config(Path(base_dir) / f"{persona_name}.yaml")
