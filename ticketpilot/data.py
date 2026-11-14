"""Create small, explicitly SYNTHETIC demonstration ticket data."""
from __future__ import annotations
import csv
import random
from pathlib import Path

CATEGORIES = {
    "access": [
        "I cannot log in to the {system} account since {when}",
        "User sign in blocked by {problem} in {system}",
        "Please reset my {system} password because {problem}",
        "MFA verification code fails for my {system} account {when}",
        "Permissions denied when opening {system} with {problem}",
        "Unable to access {system}; authentication shows {problem}",
    ],
    "billing": [
        "Invoice has a duplicate charge for {system} {when}",
        "Please correct the VAT amount on our {system} invoice",
        "Payment method rejected for {system} subscription {when}",
        "Request a refund for an incorrect {system} payment",
        "Billing statement total is wrong for {system} {when}",
        "Need a receipt for {system} plan and {problem}",
    ],
    "product": [
        "The {system} dashboard button is not working {when}",
        "Feature request: add export function to {system}",
        "Search results appear incorrect in {system} with {problem}",
        "A recent {system} update broke filter settings",
        "The {system} report chart displays stale data",
        "Request usability improvements for {system} workflow {when}",
    ],
    "infrastructure": [
        "Production {system} API reports 500 errors {when}",
        "The {system} service is unreachable due to {problem}",
        "CPU usage spiked on the {system} server {when}",
        "High database latency affects {system} requests",
        "Kubernetes pod crash loop for {system} {when}",
        "Service outage on {system} due to {problem}",
    ],
}

SYSTEMS = ["web portal", "internal platform", "mobile application", "customer dashboard", "service desk", "analytics platform", "reporting system"]
TIMES = ["today", "after the update", "this morning", "since yesterday", "during peak traffic"]
PROBLEMS = ["an error", "a timeout", "an unknown issue", "invalid settings", "a failed request"]
PREFIX = ["", "Hi team, ", "Urgent help requested: ", "Please investigate: ", "Customer reports: "]


def generate_rows(seed: int = 17, per_category: int = 150) -> list[dict[str, str]]:
    rng = random.Random(seed)
    rows = []
    for label, templates in CATEGORIES.items():
        seen = set()
        tries = 0
        while len(seen) < per_category and tries < per_category * 100:
            tries += 1
            text = (rng.choice(PREFIX) + rng.choice(templates).format(
                system=rng.choice(SYSTEMS), when=rng.choice(TIMES), problem=rng.choice(PROBLEMS)
            )).strip()
            if text.casefold() in seen:
                continue
            seen.add(text.casefold())
            rows.append({"text": text, "category": label})
    rng.shuffle(rows)
    return rows


def save_data(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = generate_rows()
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=["text", "category"])
        writer.writeheader()
        writer.writerows(rows)

if __name__ == "__main__":
    save_data(Path("data/synthetic_tickets.csv"))
