import json
from pathlib import Path

from scripts.export_openapi import main


def test_writes_schema_without_a_server(tmp_path: Path) -> None:
    output = tmp_path / "api" / "openapi.json"

    assert main(["--output", str(output)]) == 0

    schema = json.loads(output.read_text(encoding="utf-8"))
    assert schema["openapi"].startswith("3.")
    assert "/applications/{application_id}/submit" in schema["paths"]
    assert "/ready" in schema["paths"]


def test_check_tells_a_stale_file(tmp_path: Path) -> None:
    output = tmp_path / "openapi.json"

    assert main(["--output", str(output), "--check"]) == 1
    main(["--output", str(output)])
    assert main(["--output", str(output), "--check"]) == 0
    output.write_text("{}\n", encoding="utf-8")
    assert main(["--output", str(output), "--check"]) == 1
