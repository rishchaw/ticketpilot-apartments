"""Package only reviewed source/assets; never include local credentials or state."""
from pathlib import Path
import zipfile

root = Path(__file__).resolve().parents[1]
destination = root / "dist" / "ticketpilot-aws-source.zip"
destination.parent.mkdir(exist_ok=True)
root_files = [
    "README.md", "requirements-cloud.txt", "requirements-dev.txt", "Dockerfile",
    "Dockerfile.lambda", "compose.yaml", "compose.aws.yaml", ".gitignore",
    ".dockerignore", ".env.example", ".gitattributes", "AGENTS.md", "CLAUDE.md",
]
files = [root / name for name in root_files]
files += [root / "artifacts/model_numpy.npz", root / "artifacts/vectorizer.joblib", root / "data/knowledge_base.json"]
blocked = {".terraform", "__pycache__", ".pytest_cache"}
for directory in ("ticketpilot", "scripts", "tests", "monitoring", "docs", "infra", ".github", ".cursor/rules"):
    for path in (root / directory).rglob("*"):
        if not path.is_file() or blocked.intersection(path.relative_to(root).parts):
            continue
        if path.name in {"cloud.yml", "backend.ci.tf"} or path.suffix in {".pyc", ".tfvars", ".tfplan", ".tfbackend"} or ".tfstate" in path.name:
            continue
        files.append(path)
with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
    for path in sorted(files):
        archive.write(path, "ticketpilot-aws/" + path.relative_to(root).as_posix())
print(f"Source package: {destination.name} ({len(files)} files, {destination.stat().st_size:,} bytes)")
