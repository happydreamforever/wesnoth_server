"""Explicit local configuration; never discover or load a legacy .env."""
from dataclasses import dataclass, field
import json
from pathlib import Path
import re
from urllib.parse import urlsplit, parse_qs


class ConfigurationError(ValueError):
    pass


@dataclass(frozen=True)
class LocalMongo:
    """A dedicated loopback database; credentials belong to the owned runtime."""
    port: int = 27018
    name: str = "wesnoth_game"
    replica_set: str = "wesnoth-rs"

    def __post_init__(self):
        if (type(self.port) is not int or not 1024 <= self.port <= 65535
                or self.port in (15000, 15001, 15002, 18765)
                or not isinstance(self.name, str)
                or re.fullmatch(r"wesnoth_[a-z0-9_]{1,48}", self.name) is None
                or not isinstance(self.replica_set, str)
                or re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,62}", self.replica_set) is None):
            raise ConfigurationError("Invalid dedicated local MongoDB endpoint settings.")

    @classmethod
    def from_uri(cls, value):
        try:
            uri = urlsplit(value)
            query = parse_qs(uri.query, strict_parsing=True, keep_blank_values=True)
            endpoint = cls(port=uri.port, name=uri.path[1:], replica_set=query["replicaSet"][0])
            valid = (uri.scheme == "mongodb" and uri.hostname in ("127.0.0.1", "localhost")
                     and uri.username == "wesnoth_app" and bool(uri.password)
                     and uri.path == "/" + endpoint.name and not uri.fragment
                     and query == {"authSource": [endpoint.name], "replicaSet": [endpoint.replica_set],
                                   "directConnection": ["true"]})
            if not valid:
                raise ValueError()
            return endpoint
        except (ValueError, TypeError, KeyError, IndexError):
            raise ConfigurationError("Expected a dedicated authenticated local Alliance database configuration.") from None


@dataclass(frozen=True)
class Settings:
    mongo_uri: str = field(repr=False)
    secret_key: str = field(repr=False)
    bridge_secret: str = field(repr=False)
    host: str = "127.0.0.1"
    port: int = 18765

    def __post_init__(self):
        LocalMongo.from_uri(self.mongo_uri)
        if self.host != "127.0.0.1" or self.port != 18765:
            raise ConfigurationError("Alliance HTTP must use 127.0.0.1:18765 in this release.")
        if not all(isinstance(s, str) and re.fullmatch(r"[A-Za-z0-9_-]{43,128}", s)
                   for s in (self.secret_key, self.bridge_secret)):
            raise ConfigurationError("Runtime secret format is invalid. Keep the runtime backup.")
        if self.secret_key == self.bridge_secret:
            raise ConfigurationError("Browser and native bridge credentials must be separate.")

    @property
    def database(self):
        return LocalMongo.from_uri(self.mongo_uri)

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
