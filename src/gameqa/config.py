import os
from pathlib import Path
import tomllib


def load_config(path=None):
    chosen = path or os.environ.get("GAMEQA_CONFIG")
    if not chosen:
        raise ValueError("Set GAMEQA_CONFIG or pass --config; see config.example.toml")
    source = Path(chosen).resolve()
    with source.open("rb") as stream:
        config = tomllib.load(stream)
    config["_path"] = str(source)
    config["_base"] = source.parent
    return config


def resolve_path(config, value):
    path = Path(os.path.expandvars(value)).expanduser()
    return path.resolve() if path.is_absolute() else (config["_base"] / path).resolve()
