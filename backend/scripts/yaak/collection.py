"""Models of a Yaak workspace and the files Yaak reads them from.

Open Folder takes one YAML file per model (`yaak.<id>.yaml`) and keeps the
folder in sync; Import takes the same models as one JSON. Ids come from stable
keys, so a run after an API change rewrites only what changed.
"""

import hashlib
import json
from collections import defaultdict
from collections.abc import Sequence
from typing import Any

import yaml

YAAK_VERSION = "2026.9.0"
EXPORT_SCHEMA = 4
# Siblings are sorted by sortPriority, then by updatedAt: one fixed time keeps the files stable.
TIMESTAMP = "2026-10-24T00:00:00"

_ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
_EXPORT_KEYS = {
    "workspace": "workspaces",
    "environment": "environments",
    "folder": "folders",
    "http_request": "httpRequests",
}


def model_id(prefix: str, key: str) -> str:
    """`<prefix>_` and ten base62 characters, like the ids Yaak makes itself."""
    number = int.from_bytes(hashlib.sha1(key.encode()).digest(), "big")
    chars = []
    for _ in range(10):
        number, rest = divmod(number, 62)
        chars.append(_ALPHABET[rest])
    return f"{prefix}_{''.join(chars)}"


def var(name: str) -> str:
    return f"${{[ {name} ]}}"


def answer(request_id: str, path: str, *, behavior: str = "smart", ttl: int | None = None) -> str:
    """A field of the latest response of a request, by JSONPath.

    `smart` sends the request first when it has no response yet, `always` sends it on every
    use, `ttl` sends it again when the response is older than `ttl` seconds.
    """
    args = [f"request='{request_id}'", f"behavior='{behavior}'"]
    if ttl is not None:
        args.append(f"ttl='{ttl}'")
    args.append(f"path='{_quote(path)}'")
    return f"${{[ response.body.path({', '.join(args)}) ]}}"


def _quote(text: str) -> str:
    return text.replace("\\", "\\\\").replace("'", "\\'")


class Raw(str):
    """A template that goes into a JSON body without quotes, e.g. a number from a response."""


def json_text(body: Any) -> str:
    raws: list[str] = []

    def mark(value: Any) -> Any:
        if isinstance(value, Raw):
            raws.append(value)
            return f"@@raw{len(raws) - 1}@@"
        if isinstance(value, dict):
            return {key: mark(item) for key, item in value.items()}
        if isinstance(value, list):
            return [mark(item) for item in value]
        return value

    text = json.dumps(mark(body), ensure_ascii=False, indent=2)
    for index, raw in enumerate(raws):
        text = text.replace(f'"@@raw{index}@@"', raw)
    return text


def bearer(token: str) -> dict[str, Any]:
    return {
        "authenticationType": "bearer",
        "authentication": {"token": token, "prefix": "Bearer"},
    }


NO_AUTH: dict[str, Any] = {"authenticationType": "none", "authentication": {}}


class Collection:
    """One workspace: its environments, folders and HTTP requests."""

    def __init__(self, key: str, name: str, description: str) -> None:
        self.workspace_id = model_id("wk", key)
        self.models: list[dict[str, Any]] = [
            {
                "model": "workspace",
                "id": self.workspace_id,
                "name": name,
                "description": description,
                **_times(),
                **NO_AUTH,
            }
        ]
        self._order: dict[str, int] = defaultdict(int)

    def environment(
        self,
        key: str,
        name: str,
        variables: dict[str, str],
        *,
        parent_model: str = "workspace",
        parent_id: str | None = None,
        color: str | None = None,
    ) -> str:
        environment_id = model_id("ev", key)
        self.models.append(
            {
                "model": "environment",
                "id": environment_id,
                "workspaceId": self.workspace_id,
                "name": name,
                "public": True,  # only public environments go into the synced folder
                "parentModel": parent_model,
                "parentId": parent_id,
                "variables": [
                    {"enabled": True, "name": variable, "value": value}
                    for variable, value in variables.items()
                ],
                "color": color,
                "sortPriority": self._next(f"env:{parent_model}:{parent_id}"),
                **_times(),
            }
        )
        return environment_id

    def folder(self, key: str, name: str, *, parent: str | None, description: str = "") -> str:
        folder_id = model_id("fl", key)
        self.models.append(
            {
                "model": "folder",
                "id": folder_id,
                "workspaceId": self.workspace_id,
                "folderId": parent,
                "name": name,
                "description": description,
                "sortPriority": self._next(parent or self.workspace_id),
                "authenticationType": None,  # inherit
                "authentication": {},
                **_times(),
            }
        )
        return folder_id

    def request(
        self,
        request_id: str,
        name: str,
        method: str,
        url: str,
        *,
        folder: str,
        auth: dict[str, Any],
        description: str = "",
        params: Sequence[tuple[str, str, bool]] = (),
        headers: Sequence[tuple[str, str]] = (),
        body: Any = None,
        content_type: str = "application/json",
    ) -> str:
        model: dict[str, Any] = {
            "model": "http_request",
            "id": request_id,
            "workspaceId": self.workspace_id,
            "folderId": folder,
            "name": name,
            "description": description,
            "method": method,
            "url": url,
            "urlParameters": [
                {"enabled": enabled, "name": param, "value": value}
                for param, value, enabled in params
            ],
            "headers": [{"enabled": True, "name": h, "value": v} for h, v in headers],
            "bodyType": None,
            "body": {},
            "sortPriority": self._next(folder),
            **auth,
            **_times(),
        }
        if body is not None:
            text = body if isinstance(body, str) else json_text(body)
            model["bodyType"] = content_type
            model["body"] = {"text": text}
            model["headers"].append(
                {"enabled": True, "name": "Content-Type", "value": content_type}
            )
        self.models.append(model)
        return request_id

    def _next(self, parent: str) -> float:
        self._order[parent] += 1
        return float(self._order[parent] * 1000)

    def files(self) -> dict[str, str]:
        """File name → YAML, as Yaak writes the synced folder."""
        return {
            f"yaak.{model['id']}.yaml": yaml.dump(
                {"type": model["model"], **model},
                Dumper=_Dumper,
                allow_unicode=True,
                sort_keys=False,
                width=10_000,
            )
            for model in self.models
        }

    def export(self) -> str:
        """The JSON for Import: the same models, grouped by kind."""
        resources: dict[str, list[dict[str, Any]]] = {key: [] for key in _EXPORT_KEYS.values()}
        for model in self.models:
            resources[_EXPORT_KEYS[model["model"]]].append(model)
        data = {
            "yaakVersion": YAAK_VERSION,
            "yaakSchema": EXPORT_SCHEMA,
            "timestamp": TIMESTAMP,
            "resources": resources,
        }
        return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


def _times() -> dict[str, str]:
    return {"createdAt": TIMESTAMP, "updatedAt": TIMESTAMP}


class _Dumper(yaml.SafeDumper):
    """Multi-line strings (bodies, descriptions) as `|` blocks: readable in a diff."""


def _represent_str(dumper: yaml.SafeDumper, value: str) -> yaml.ScalarNode:
    style = "|" if "\n" in value else None
    return dumper.represent_scalar("tag:yaml.org,2002:str", value, style=style)


_Dumper.add_representer(str, _represent_str)
