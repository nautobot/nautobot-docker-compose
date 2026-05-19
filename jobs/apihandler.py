"""ApiHandler Module."""

from functools import cached_property
from typing import Any

import httpx

from .credentials import Env, get_environment


class ApiHandlerError(Exception):
    """ApiHandler Error."""


class ApiHandler:
    """Apihandler Class."""

    def __init__(
        self,
        url: str,
        headers: dict[str, str] | None = None,
    ) -> None:
        """__init__."""
        self.headers = headers
        self.url = url

    @cached_property
    def environment(self) -> Env:
        """Environment Property."""
        return get_environment()

    @cached_property
    def client(self) -> httpx.Client:
        """Client Property."""
        return httpx.Client(base_url=self.url, headers=self.headers)

    def get(
        self, endpoint: str, params: dict[str, Any] | None = None
    ) -> httpx.Response:
        """GET Request Method."""
        try:
            return self.client.get(endpoint, params=params).raise_for_status()
        except httpx.HTTPError as e:
            raise ApiHandlerError("API request failed") from e

    def patch(
        self,
        endpoint: str,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> httpx.Response:
        """PATCH Request Method."""
        try:
            return self.client.patch(
                endpoint, json=json, params=params
            ).raise_for_status()
        except httpx.HTTPError as e:
            raise ApiHandlerError("API request failed") from e

    def post(
        self,
        endpoint: str,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> httpx.Response:
        """POST Request Method."""
        try:
            return self.client.post(
                endpoint, json=json, params=params
            ).raise_for_status()
        except httpx.HTTPError as e:
            raise ApiHandlerError("API request failed") from e

    def post_all(
        self,
        endpoint: str,
        json: list[dict[str, Any]] | None = None,
        params: dict[str, Any] | None = None,
    ) -> httpx.Response:
        """POST All Request Method."""
        try:
            return self.client.post(
                endpoint, json=json, params=params
            ).raise_for_status()
        except httpx.HTTPError as e:
            raise ApiHandlerError("API request failed") from e

    def put(
        self,
        endpoint: str,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> httpx.Response:
        """PUT Request Method."""
        try:
            return self.client.put(
                endpoint, json=json, params=params
            ).raise_for_status()
        except httpx.HTTPError as e:
            raise ApiHandlerError("API request failed") from e

    def delete(self, endpoint: str) -> httpx.Response:
        """DELETE Request Method."""
        try:
            return self.client.delete(endpoint).raise_for_status()
        except httpx.HTTPError as e:
            raise ApiHandlerError("API request failed") from e
