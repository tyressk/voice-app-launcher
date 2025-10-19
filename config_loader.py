import os
from pathlib import Path
from typing import Any, Dict
import logging_module
import tomllib

CONFIG_PATH = "voice_app_launcher"

class ConfigSchemaError(RuntimeError):
    """Raised when a configuration file is present but missing required fields."""

def _default_config() -> Dict[str, Any]:
    model_default_path = Path.cwd() / "models"
    browser = str(model_default_path / "Open_Browser.onnx")
    editor = str(model_default_path / "Open_Editor.onnx")
    terminal = str(model_default_path / "Open_Terminal.onnx")
    youtube = str(model_default_path / "Open_Youtube.onnx")
    return {
        "general": {
            "model_paths": [browser,editor,terminal,youtube],
            "sensitivity": 0.5,
            "log_level": "INFO",
            "launch_cooldown_secs": 3.0
        },
        # Top-level mapping of wakeword name -> list of commands to launch
        "wakewords": {
            "\"Open_Terminal\"" : ["wezterm start --always-new-process"],
            "\"Open_Browser\"" : ["firefox"],
            "\"Open_Editor\"" : ["code"],
            "\"Open_Youtube\"" : ["firefox --new-tab https://www.youtube.com"]
        },
        "audio": {
            "sample_rate": 16000,
            "channels": 1,
            "chunk_size": 1280
        },
    }


DEFAULT_CONFIG: Dict[str, Any] = _default_config()


def _get_config_path() -> Path:
    """Return the expanded Path to the user's config.toml."""

    return Path(os.path.expanduser("~")) / ".config" / CONFIG_PATH / "config.toml"


def read_config(path: Path) -> Dict[str, Any]:
    """Read and validate TOML config from path and return as dict."""

    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    # Read TOML with stdlib tomllib
    try:
        with path.open("rb") as fh:
            cfg = tomllib.load(fh)
    except Exception as exc:  # parsing error or IO error
        raise RuntimeError(f"Failed to parse TOML config at {path}: {exc}") from exc

    if cfg is None:
        raise RuntimeError(f"TOML config at {path} is empty or invalid")

    if not isinstance(cfg, dict):
        raise RuntimeError(f"Unexpected TOML top-level type in {path}: {type(cfg)!r}")

    gen = cfg.get("general")
    wakewords = cfg.get("wakewords")
    audio = cfg.get("audio")

    missing: list[str] = []

    if not isinstance(gen, dict):
        missing.extend(["general.model_paths", "general.sensitivity"])
    else:
        if "model_paths" not in gen:
            missing.append("general.model_paths")
        if "sensitivity" not in gen:
            missing.append("general.sensitivity")
        if "launch_cooldown_secs" not in gen:
            missing.append("general.launch_cooldown_secs")

    if not isinstance(wakewords, dict):
        missing.append("wakewords")

    if not isinstance(audio, dict):
        missing.extend(["audio.sample_rate", "audio.channels", "audio.chunk_size"])
    else:
        if "sample_rate" not in audio:
            missing.append("audio.sample_rate")
        if "channels" not in audio:
            missing.append("audio.channels")
        if "chunk_size" not in audio:
            missing.append("audio.chunk_size")

    if missing:
        raise ConfigSchemaError((f"Config at {path} is missing required keys: {', '.join(missing)}. " 
                                "Please fix config.toml file or delete it to create a default version."))

    return cfg


def _serialize_simple_toml(obj: Any, prefix: str | None = None) -> str:
    """Serialize (some) Python types to TOML."""

    def _fmt_value(v: Any) -> str:
        if v is None:
            return "null"
        if isinstance(v, bool):
            return "true" if v else "false"
        if isinstance(v, (int, float)):
            return repr(v)
        if isinstance(v, str):
            # basic safe quoting; escape backslashes and quotes
            esc = v.replace("\\", "\\\\").replace('"', '\\"')
            return f'"{esc}"'
        if isinstance(v, list):
            return "[" + ", ".join(_fmt_value(i) for i in v) + "]"
        raise TypeError(f"Unsupported type for TOML serialization: {type(v)!r}")

    if prefix is None:
        prefix = ""

    lines: list[str] = []

    # Top-level dict
    if not isinstance(obj, dict):
        raise TypeError("Top-level TOML object must be a dict")

    # First pass: write simple key = value pairs at this table level
    simple_items = {k: v for k, v in obj.items() if not isinstance(v, dict)}
    table_items = {k: v for k, v in obj.items() if isinstance(v, dict)}

    for k, v in simple_items.items():
        lines.append(f"{k} = {_fmt_value(v)}")

    # Then write tables
    for table_name, table_val in table_items.items():
        lines.append("")
        lines.append(f"[{table_name}]")
        if not isinstance(table_val, dict):
            raise TypeError("Table value must be a dict")
        for k, v in table_val.items():
            if isinstance(v, dict):
                lines.append("")
                lines.append(f"[{table_name}.{k}]")
                for kk, vv in v.items():
                    lines.append(f"{kk} = {_fmt_value(vv)}")
            else:
                lines.append(f"{k} = {_fmt_value(v)}")

    return "\n".join(lines) + "\n"


def write_config(path: Path, config: Dict[str, Any]) -> None:
    "Write the given config dict to path as TOML."

    parent = path.parent
    try:
        parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise RuntimeError(f"Failed to create config directory {parent}: {exc}") from exc

    toml_text = _serialize_simple_toml(config)

    # Write atomically to avoid partial writes
    tmp = parent / (path.name + ".tmp")
    try:
        with tmp.open("w", encoding="utf-8") as fh:
            fh.write(toml_text)
            fh.flush()
            os.fsync(fh.fileno())
        # Replace existing file
        tmp.replace(path)
    except OSError as exc:
        # Clean up temp file on failure
        try:
            if tmp.exists():
                tmp.unlink()
        except Exception:
            pass
        raise RuntimeError(f"Failed to write config to {path}: {exc}") from exc


def ensure_config(defaults: Dict[str, Any]) -> Path:
    """Ensure config file exists. 
    If the file doesn't exist create with `defaults`
    """

    path = _get_config_path()

    if not path.exists():
        write_config(path, defaults)
        return path

    try:
        _ = read_config(path)
        return path
    except FileNotFoundError:
        write_config(path, defaults)
        return path
    except RuntimeError as exc:
        raise exc


def load_config() -> Dict[str, Any]:
    """Ensure the config exists and return the loaded configuration."""

    path = ensure_config(DEFAULT_CONFIG)
    try:
        cfg = read_config(path)
    except RuntimeError as exc:
        logger = logging_module.get_logger()
        logger.error(f"Warning: failed to parse config: {exc}")
        raise exc
    return cfg