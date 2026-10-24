import json
import re
from pathlib import Path
from typing import Any

import pytest
import yaml

from scripts.export_yaak import DEFAULT_OPENAPI, build, main
from scripts.yaak.reference import ref

_REQUEST = re.compile(r"request='(rq_\w+)'")
_VARIABLE = re.compile(r"\$\{\[\s*([A-Za-z_]\w*)\s*\]\}")


@pytest.fixture(scope="module")
def models() -> list[dict[str, Any]]:
    return build(json.loads(DEFAULT_OPENAPI.read_text(encoding="utf-8"))).models


def by_model(models: list[dict[str, Any]], kind: str) -> list[dict[str, Any]]:
    return [m for m in models if m["model"] == kind]


def test_writes_the_folder_and_the_export(tmp_path: Path) -> None:
    folder, export = tmp_path / "yaak", tmp_path / "yaak.json"

    assert main(["--folder", str(folder), "--export", str(export)]) == 0

    files = sorted(folder.glob("yaak.*.yaml"))
    parsed = [yaml.safe_load(f.read_text(encoding="utf-8")) for f in files]
    assert all(
        m["type"] == m["model"] and f.name == f"yaak.{m['id']}.yaml"
        for f, m in zip(files, parsed, strict=True)
    )
    data = json.loads(export.read_text(encoding="utf-8"))
    assert data["yaakSchema"] == 4
    exported = [m for resource in data["resources"].values() for m in resource]
    # Open Folder and Import read the same models: bodies and templates survive the YAML.
    for model in parsed:
        del model["type"]
    assert {m["id"]: m for m in parsed} == {m["id"]: m for m in exported}
    [workspace] = data["resources"]["workspaces"]
    assert {m["workspaceId"] for m in exported if m["model"] != "workspace"} == {workspace["id"]}


def test_every_operation_has_a_request_in_the_reference(models: list[dict[str, Any]]) -> None:
    openapi = json.loads(DEFAULT_OPENAPI.read_text(encoding="utf-8"))
    requests = {m["id"]: m for m in by_model(models, "http_request")}

    for path, operations in openapi["paths"].items():
        for method in operations:
            request = requests[ref(method, path)]
            assert request["method"] == method.upper()
            assert request["url"].endswith(re.sub(r"\{(\w+)\}", r":\1", path))


def test_templates_point_to_requests_and_variables_in_scope(models: list[dict[str, Any]]) -> None:
    request_ids = {m["id"] for m in by_model(models, "http_request")}
    parents = {m["id"]: m["folderId"] for m in by_model(models, "folder")}
    scoped: dict[str | None, set[str]] = {None: set()}
    for environment in by_model(models, "environment"):
        names = {v["name"] for v in environment["variables"]}
        owner = environment["parentId"] if environment["parentModel"] == "folder" else None
        scoped.setdefault(owner, set()).update(names)
        for value in environment["variables"]:
            assert set(_REQUEST.findall(value["value"])) <= request_ids, environment["name"]

    for request in by_model(models, "http_request"):
        visible = set(scoped[None])
        folder = request["folderId"]
        while folder is not None:
            visible |= scoped.get(folder, set())
            folder = parents[folder]
        text = json.dumps(request, ensure_ascii=False)
        assert set(_REQUEST.findall(text)) <= request_ids, request["name"]
        assert set(_VARIABLE.findall(text)) <= visible, request["name"]


def test_an_announced_file_is_as_long_as_the_uploaded_one(models: list[dict[str, Any]]) -> None:
    requests = {m["id"]: m for m in by_model(models, "http_request")}
    uploads = [
        r for r in requests.values() if r["method"] == "PUT" and r["url"].startswith("${[ response")
    ]

    assert uploads
    for upload in uploads:
        [announce_id] = _REQUEST.findall(upload["url"])
        announced = json.loads(requests[announce_id]["body"]["text"])
        assert announced["size_bytes"] == len(upload["body"]["text"].encode()), upload["name"]
        assert announced["content_type"] == upload["bodyType"]


def test_scenario_steps_are_numbered_in_their_order(models: list[dict[str, Any]]) -> None:
    folders = [f for f in by_model(models, "folder") if re.match(r"S-\d+\. ", f["name"])]
    assert len(folders) == 10

    for folder in folders:
        steps = sorted(
            (r for r in by_model(models, "http_request") if r["folderId"] == folder["id"]),
            key=lambda r: r["sortPriority"],
        )
        assert [s["name"][:2] for s in steps] == [f"{n:02d}" for n in range(1, len(steps) + 1)]


def test_check_tells_a_stale_collection(tmp_path: Path) -> None:
    args = ["--folder", str(tmp_path / "yaak"), "--export", str(tmp_path / "yaak.json")]

    assert main([*args, "--check"]) == 1
    main(args)
    assert main([*args, "--check"]) == 0
    next((tmp_path / "yaak").glob("yaak.*.yaml")).write_text("{}\n", encoding="utf-8")
    assert main([*args, "--check"]) == 1
