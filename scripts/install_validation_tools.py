"""Download project-local Terraform/promtool and verify published SHA-256 sums."""
import hashlib
import io
from pathlib import Path
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1] / ".tools"
ROOT.mkdir(exist_ok=True)


def fetch(url):
    with urllib.request.urlopen(url, timeout=30) as response:
        return response.read()


def install(base_url, archive_name, sums_name, output, member):
    if output.exists():
        print(f"Already present: {output.name}")
        return
    checksums = fetch(base_url + "/" + sums_name).decode()
    expected = next(line.split()[0] for line in checksums.splitlines() if line.split()[-1].lstrip("*") == archive_name)
    archive = fetch(base_url + "/" + archive_name)
    if hashlib.sha256(archive).hexdigest() != expected:
        raise RuntimeError("Download checksum mismatch")
    with zipfile.ZipFile(io.BytesIO(archive)) as zipped:
        output.write_bytes(zipped.read(member))
    print(f"Installed and checksum-verified: {output.name}")


install("https://releases.hashicorp.com/terraform/1.13.5", "terraform_1.13.5_windows_amd64.zip", "terraform_1.13.5_SHA256SUMS", ROOT / "terraform.exe", "terraform.exe")
install("https://github.com/prometheus/prometheus/releases/download/v3.5.0", "prometheus-3.5.0.windows-amd64.zip", "sha256sums.txt", ROOT / "promtool.exe", "prometheus-3.5.0.windows-amd64/promtool.exe")
