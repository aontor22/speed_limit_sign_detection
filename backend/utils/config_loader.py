import yaml
from pathlib import Path


class DotDict(dict):
    """
    A dict subclass that allows attribute-style (dot-notation) access.

    Example:
        d = DotDict({"a": {"b": 1}})
        d.a.b  # → 1
    """
    def __getattr__(self, key):
        try:
            val = self[key]
            # Recursively wrap nested dicts
            if isinstance(val, dict):
                return DotDict(val)
            return val
        except KeyError:
            raise AttributeError(f"Config key '{key}' not found.")

    def __setattr__(self, key, value):
        self[key] = value

    def __delattr__(self, key):
        try:
            del self[key]
        except KeyError:
            raise AttributeError(f"Config key '{key}' not found.")

    def get_nested(self, *keys, default=None):
        """
        Safely get a nested key.
        Example: cfg.get_nested('model', 'confidence_threshold', default=0.5)
        """
        val = self
        for k in keys:
            if isinstance(val, (dict, DotDict)):
                val = val.get(k)
                if val is None:
                    return default
            else:
                return default
        return val


def load_config(config_path: str = "config.yaml") -> DotDict:
    """
    Load YAML config file and return as a DotDict.

    Args:
        config_path: Path to the YAML configuration file.

    Returns:
        DotDict with configuration values accessible via dot notation.

    Raises:
        FileNotFoundError: If config file does not exist.
        ValueError: If YAML is malformed.
    """
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(
            f"Config file not found: {config_path}\n"
            "Please ensure 'config.yaml' is in the project root."
        )

    with open(path, "r") as f:
        try:
            raw = yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise ValueError(f"Invalid YAML in config file: {e}")

    if not isinstance(raw, dict):
        raise ValueError("Config file must contain a YAML mapping at the top level.")

    return _deep_dotdict(raw)


def _deep_dotdict(obj):
    """Recursively convert nested dicts to DotDicts."""
    if isinstance(obj, dict):
        return DotDict({k: _deep_dotdict(v) for k, v in obj.items()})
    if isinstance(obj, list):
        return [_deep_dotdict(i) for i in obj]
    return obj
