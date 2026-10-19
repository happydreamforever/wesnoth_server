"""Explicit local configuration; never discover or load a legacy .env."""
from dataclasses import dataclass, field
import json
from pathlib import Path
import re
from urllib.parse import urlsplit, parse_qs


class ConfigurationError(ValueError):
    pass


@dataclass(frozen=True)
class Settings:
    mongo_uri: str = field(repr=False)
    secret_key: str = field(repr=False)
    bridge_secret: str = field(repr=False)
    host: str = "127.0.0.1"
    port: int = 18765

    def __post_init__(self):
        try:
            uri = urlsplit(self.mongo_uri)
            query = parse_qs(uri.query, strict_parsing=True)
            valid = (uri.scheme == "mongodb" and uri.hostname in ("127.0.0.1", "localhost")
                     and uri.port == 27018 and uri.username == "wesnoth_app" and bool(uri.password)
                     and uri.path == "/wesnoth_game" and not uri.fragment
                     and query == {"authSource": ["wesnoth_game"], "replicaSet": ["wesnoth-rs"],
                                   "directConnection": ["true"]})
        except (ValueError, TypeError):
            valid = False
        if not valid:
            raise ConfigurationError("Expected the dedicated local Alliance database configuration.")
        if self.host != "127.0.0.1" or self.port != 18765:
            raise ConfigurationError("Alliance HTTP must use 127.0.0.1:18765 in this release.")
        if not all(isinstance(s, str) and re.fullmatch(r"[A-Za-z0-9_-]{43,128}", s)
                   for s in (self.secret_key, self.bridge_secret)):
            raise ConfigurationError("Runtime secret format is invalid. Keep the runtime backup.")
        if self.secret_key == self.bridge_secret:
            raise ConfigurationError("Browser and native bridge credentials must be separate.")

    @classmethod
    def load(cls, runtime):
        path = Path(runtime) / "config.json"
        if path.is_symlink():
            raise ConfigurationError("Runtime configuration must be an ordinary local file.")
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or data.get("format") != 1 or data.get("purpose") != "wesnoth-alliance-local":
                raise ConfigurationError("Unsupported Alliance runtime configuration.")
            return cls(**data["service"])
        except (OSError, ValueError, TypeError, KeyError):
            raise ConfigurationError("Cannot load Alliance configuration; run initialization first.") from None
