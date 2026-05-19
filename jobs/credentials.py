"""Credentials Module."""

import re
import socket
from dataclasses import dataclass, field
from enum import StrEnum, auto
from pathlib import Path

from httpx import Client
from nautobot.extras.models import Secret


class CredentialsError(Exception):
    """Credentials Error."""


class Env(StrEnum):
    """Environment Enum."""

    LAB = auto()
    NONPROD = auto()
    PROD = auto()


def get_hostname() -> str:
    """Hostname Property."""
    hostname = socket.gethostname()
    if not hostname:
        raise CredentialsError("Hostname could not be determined.")
    return hostname


def get_environment() -> Env:
    """Environment Property."""
    hostname = get_hostname()
    if re.search(r"nonprod", hostname):
        environment = Env.NONPROD
    elif re.search(r"prod", hostname):
        environment = Env.PROD
    else:
        environment = Env.LAB
    return environment


@dataclass(kw_only=True)
class Credentials:
    """Apigee Dataclass."""

    path: Path = field(init=False)
    environment: Env = field(default_factory=get_environment)

    def get_secret(self, key: str) -> str:
        """Get Secret Method."""
        path = Path("/opt/nautobot/pkg/.secrets")
        if self.environment == Env.LAB:
            secret = Path(path / f"{key}").read_text(encoding="utf-8").strip()
        else:
            secret = Secret.objects.get(name=key).get_value()
        return secret


@dataclass(kw_only=True)
class P42ApigeeCredentials(Credentials):
    """Project42 API Apigee Dataclass."""

    url: str = field(init=False)
    key: str = field(init=False)
    secret: str = field(init=False)

    def __post_init__(self) -> None:
        """Post Init Method."""
        if self.environment == Env.LAB:
            self.url = self.get_secret(key="apigee_url")
            self.key = self.get_secret(key="p42_api_key")
            self.secret = self.get_secret(key="p42_api_secret")
        else:
            self.url = self.get_secret(key="Apigee URL")
            self.key = self.get_secret(key="P42 API Key")
            self.secret = self.get_secret(key="P42 API Secret")

    @property
    def headers(self) -> dict[str, str]:
        """Get Apigee Headers Function."""
        payload = {
            "client_id": self.key,
            "client_secret": self.secret,
            "grant_type": "client_credentials",
        }
        with Client() as client:
            response = client.post(self.url, json=payload).raise_for_status()
            token = response.json()["token"]
            if not token:
                raise CredentialsError("Failed to retrieve Apigee token.")
            return {
                "Accept": "application/json; indent=4",
                "Content-Type": "application/json",
                "Authorization": f"Bearer {token}",
            }
