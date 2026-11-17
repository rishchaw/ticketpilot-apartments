"""Package reviewed source/assets without local credentials, generated plans, or state."""
from __future__ import annotations

from fnmatch import fnmatchcase
import json
from pathlib import Path
import zipfile

ROOT_FILES = (
    "README.md", "requirements-cloud.txt", "requirements-dev.txt", "requirements-gcp.txt",
    "Dockerfile", "Dockerfile.lambda", "Dockerfile.gcp", "compose.yaml", "compose.aws.yaml",
    ".gitignore", ".dockerignore", ".env.example", ".gitattributes", "AGENTS.md", "CLAUDE.md",
)
ASSET_FILES = ("artifacts/model_numpy.npz", "artifacts/vectorizer.joblib", "data/knowledge_base.json")
SOURCE_DIRECTORIES = ("ticketpilot", "scripts", "tests", "monitoring", "docs", "infra", "deploy", ".github", ".cursor/rules")
BLOCKED_DIRECTORIES = {".terraform", "__pycache__", ".pytest_cache", ".tools", ".venv", ".secrets", ".aws", ".gcloud", ".git", "dist"}
BLOCKED_PATTERNS = (
    "*.pyc", "*.tfvars", "*.tfvars.json", "*.tfplan", "*.tfbackend", "*.tfstate*",
    "*.db", "*.db-shm", "*.db-wal", "*.pem", "*.key", "*.p12", "*.pfx",
    "gha-creds-*.json", "application_default_credentials.json", "credentials.json",
    "*-credentials.json", "credentials-*.json", "service-account*.json", "*-service-account*.json",
    "deployment-plan.json", "deployment-gcp-plan.json", "terraform-plan.json",
    "backend.ci.tf", "backend.gcp.ci.tf", "backend.generated.tf", "*.generated.tf",
)
CREDENTIAL_TYPES = {"service_account", "authorized_user", "external_account", "external_account_authorized_user"}
SECRET_FIELDS = {"private_key", "client_secret", "access_token", "refresh_token", "aws_secret_access_key", "aws_session_token"}


def _generated_json(path: Path) -> bool:
    """Recognize credential/state/plan structures without printing their contents."""
    if path.suffix.lower() != ".json":
        return False
    try:
        document = json.loads(path.read_text(encoding="utf-8-sig"))
    except (UnicodeError, json.JSONDecodeError):
        return False
    if not isinstance(document, dict):
        return False
    credential_type = document.get("type")
    if (isinstance(credential_type, str) and credential_type in CREDENTIAL_TYPES) or SECRET_FIELDS.intersection(document):
        return True
    if "format_version" in document and any(key in document for key in ("planned_values", "resource_changes", "prior_state")):
        return True
    return "lineage" in document and "serial" in document and "resources" in document


def is_source_file(path: Path, root: Path) -> bool:
    relative = path.relative_to(root)
    if BLOCKED_DIRECTORIES.intersection(part.lower() for part in relative.parts) or path.is_symlink():
        return False
    name = path.name.lower()
    if name == "cloud.yml" or (name.startswith(".env") and name != ".env.example"):
        return False
    if any(fnmatchcase(name, pattern) for pattern in BLOCKED_PATTERNS):
        return False
    if not path.is_file():
        return False
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return not _generated_json(path)


def collect_source_files(root: Path) -> list[Path]:
    """Keep an explicit root/asset allowlist and filtered source directories."""
    files = {root / name for name in ROOT_FILES + ASSET_FILES}
    for path in files:
        if not path.is_file():
            raise FileNotFoundError("Missing required source file: " + str(path.relative_to(root)))
    for directory in SOURCE_DIRECTORIES:
        files.update((root / directory).rglob("*"))
    return sorted(path for path in files if is_source_file(path, root))


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    destination = root / "dist" / "ticketpilot-aws-source.zip"
    files = collect_source_files(root)
    destination.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path, "ticketpilot-aws/" + path.relative_to(root).as_posix())
    print(f"Source package: {destination.name} ({len(files)} files, {destination.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
