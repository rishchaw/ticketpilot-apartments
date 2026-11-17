"""A queue replacement between API read/write must return 409 and preserve it."""
from copy import deepcopy
from types import SimpleNamespace
from fastapi.testclient import TestClient
from ticketpilot import storage
from ticketpilot.api import app


def test_legacy_api_queue_replacement_race_returns_conflict_without_overwriting_private_concern(monkeypatch):
    class ConditionalWriteLostRace(Exception):
        pass

    legacy = {"id": "fictional-race-id", "queue": "tickets", "title": "Synthetic old ticket",
              "text": "Synthetic legacy description", "sources": [], "requires_human_review": False,
              "status": "open", "created_at": "2026-11-17T00:00:00Z", "updated_at": "2026-11-17T00:00:00Z"}
    concern = {"id": legacy["id"], "queue": "apartment_tickets", "kind": "apartment_ticket",
               "title": "Synthetic private concern", "internal_notes": [{"text": "Private fictional note"}]}

    class ReplacedQueueTable:
        def __init__(self):
            self.row = deepcopy(legacy)
            self.put_attempts = 0
            self.meta = SimpleNamespace(client=SimpleNamespace(exceptions=SimpleNamespace(
                ConditionalCheckFailedException=ConditionalWriteLostRace)))

        def get_item(self, **arguments):
            assert arguments == {"Key": {"id": legacy["id"]}, "ConsistentRead": True}
            snapshot = deepcopy(self.row)
            # Another writer changes the queue after the strong read but before
            # the legacy status PATCH's conditional PutItem reaches the table.
            self.row = deepcopy(concern)
            return {"Item": snapshot}

        def put_item(self, **arguments):
            self.put_attempts += 1
            assert self.row["queue"] == "apartment_tickets"
            assert arguments["Item"]["queue"] == "tickets"
            assert "ConditionExpression" in arguments
            raise ConditionalWriteLostRace("fictional queue changed during update")

    table = ReplacedQueueTable()
    monkeypatch.setenv("STORAGE_MODE", "dynamodb")
    monkeypatch.setenv("ADMIN_TOKEN", "fictional-race-manager-code")
    monkeypatch.setattr(storage, "_dynamodb", lambda: table)
    response = TestClient(app).patch("/api/tickets/" + legacy["id"], json={"status": "resolved"},
                                    headers={"X-Admin-Token": "fictional-race-manager-code"})
    assert response.status_code == 409
    assert table.put_attempts == 1 and table.row == concern
    assert "Private fictional note" not in response.text
    assert "fictional queue changed" not in response.text
