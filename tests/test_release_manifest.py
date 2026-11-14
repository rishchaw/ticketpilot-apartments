"""Untrusted release artifacts cannot select arbitrary images or alter workflow outputs."""
import importlib.util
import json
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location("release_manifest", Path(__file__).resolve().parents[1] / "scripts/release_manifest.py")
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)

REPO = "example/ticketpilot"
COMMIT = "a" * 40
RUN = "12345"
APP_DIGEST = "sha256:" + "b" * 64
LAMBDA_DIGEST = "sha256:" + "c" * 64


def manifest():
    return release.build_manifest(REPO, COMMIT, RUN, APP_DIGEST, LAMBDA_DIGEST)


def test_build_and_validate_pin_both_images_and_provenance():
    built = release.build_manifest("Example/TicketPilot", COMMIT, RUN, APP_DIGEST, LAMBDA_DIGEST)
    assert built["repository"] == REPO
    assert built["app"] == {"image": "ghcr.io/" + REPO, "digest": APP_DIGEST}
    assert built["lambda"] == {"image": "ghcr.io/" + REPO + "-lambda", "digest": LAMBDA_DIGEST}
    validated = release.validate_manifest(built, REPO, COMMIT, RUN)
    assert validated == built and validated is not built
    validated["app"]["digest"] = "changed"
    assert built["app"]["digest"] == APP_DIGEST


@pytest.mark.parametrize("field,value", [
    ("repository", "attacker/ticketpilot"), ("repository", "Example/TicketPilot"),
    ("commit", "d" * 40), ("commit", "A" * 40),
    ("run_id", "99999"), ("run_id", 12345), ("schema_version", True), ("schema_version", 2),
])
def test_wrong_repository_commit_run_or_schema_is_rejected(field, value):
    bad = manifest()
    bad[field] = value
    with pytest.raises(ValueError):
        release.validate_manifest(bad, REPO, COMMIT, RUN)


@pytest.mark.parametrize("image", ["docker.io/example/ticketpilot", "ghcr.io/attacker/ticketpilot", "ghcr.io/example/ticketpilot:latest", "ghcr.io/example/ticketpilot@" + APP_DIGEST, "ghcr.io/example/ticketpilot\nadmin=true"])
@pytest.mark.parametrize("component", ["app", "lambda"])
def test_arbitrary_registry_image_tag_or_output_injection_is_rejected(component, image):
    bad = manifest()
    bad[component]["image"] = image
    with pytest.raises(ValueError):
        release.validate_manifest(bad, REPO, COMMIT, RUN)


@pytest.mark.parametrize("digest", ["latest", "sha256:" + "A" * 64, "sha256:" + "b" * 63, "sha256:" + "z" * 64, APP_DIGEST + "\nadmin=true", "sha512:" + "b" * 64, None])
def test_only_lowercase_immutable_digests_are_accepted(digest):
    bad = manifest()
    bad["lambda"]["digest"] = digest
    with pytest.raises(ValueError):
        release.validate_manifest(bad, REPO, COMMIT, RUN)


@pytest.mark.parametrize("repository", ["ghcr.io/example/ticketpilot", "example/ticketpilot/other", "../ticketpilot", "example/.hidden", "example/repo;id", "example/repo\nadmin=true", "example/repo "])
def test_repository_arguments_cannot_be_registry_paths_or_shell_inputs(repository):
    with pytest.raises(ValueError):
        release.build_manifest(repository, COMMIT, RUN, APP_DIGEST, LAMBDA_DIGEST)


@pytest.mark.parametrize("run_id", ["0", "01", "-1", 1, "123\nother=true"])
def test_run_id_must_be_a_canonical_positive_numeric_string(run_id):
    with pytest.raises(ValueError):
        release.build_manifest(REPO, COMMIT, run_id, APP_DIGEST, LAMBDA_DIGEST)


def test_extra_fields_are_rejected_at_both_levels():
    bad = manifest()
    bad["token"] = "not permitted"
    with pytest.raises(ValueError):
        release.validate_manifest(bad, REPO, COMMIT, RUN)
    bad = manifest()
    bad["app"]["tag"] = "latest"
    with pytest.raises(ValueError):
        release.validate_manifest(bad, REPO, COMMIT, RUN)


def test_cli_round_trip_exports_only_validated_metadata(tmp_path, monkeypatch, capsys):
    document = tmp_path / "release.json"
    outputs = tmp_path / "outputs.txt"
    monkeypatch.setenv("GITHUB_OUTPUT", str(outputs))
    monkeypatch.setenv("SOME_SECRET_TOKEN", "never-output-this")
    arguments = ["--repository", REPO, "--commit", COMMIT, "--run-id", RUN]
    assert release.main(["write", *arguments, "--app-digest", APP_DIGEST, "--lambda-digest", LAMBDA_DIGEST, "--output", str(document)]) == 0
    assert not outputs.exists()
    assert release.main(["verify", *arguments, "--path", str(document)]) == 0
    assert outputs.read_text(encoding="utf-8").splitlines() == [
        "commit=" + COMMIT, "app_ref=ghcr.io/" + REPO + "@" + APP_DIGEST,
        "lambda_ref=ghcr.io/" + REPO + "-lambda@" + LAMBDA_DIGEST, "run_id=" + RUN,
    ]
    output = capsys.readouterr()
    assert "never-output-this" not in output.out + output.err


def test_failed_verification_never_writes_github_outputs(tmp_path, monkeypatch):
    document = tmp_path / "release.json"
    outputs = tmp_path / "outputs.txt"
    monkeypatch.setenv("GITHUB_OUTPUT", str(outputs))
    bad = manifest()
    bad["app"]["digest"] = APP_DIGEST + "\nmalicious=true"
    document.write_text(json.dumps(bad), encoding="utf-8")
    assert release.main(["verify", "--repository", REPO, "--commit", COMMIT, "--run-id", RUN, "--path", str(document)]) == 1
    assert not outputs.exists()


def test_duplicate_json_keys_are_rejected(tmp_path, monkeypatch):
    document = tmp_path / "release.json"
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    text = json.dumps(manifest()).replace('"schema_version": 1', '"schema_version": 2, "schema_version": 1')
    document.write_text(text, encoding="utf-8")
    assert release.main(["verify", "--repository", REPO, "--commit", COMMIT, "--run-id", RUN, "--path", str(document)]) == 1
