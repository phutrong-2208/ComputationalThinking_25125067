"""Exercise the supplied local event-driven demo with live model calls.

Only the course's simulated Jira/Confluence state is modified. Each invocation
uses a new data directory and leaves the ticket ready for human review.
"""
from datetime import datetime, timezone
import json
from pathlib import Path
from uuid import uuid4


def run_demo():
    import data_store as store

    root = Path(__file__).resolve().parent
    data = root / "student_practice_data" / uuid4().hex[:8]
    data.mkdir(parents=True)
    store.DATA_DIR = data
    store.PAGES_PATH = data / "pages.json"
    store.TICKETS_PATH = data / "tickets.json"
    store.RUNS_PATH = data / "analysis_runs.json"
    store.seed_if_missing()

    import app as demo
    demo.app.config["TESTING"] = True
    client = demo.app.test_client()
    for route in ["/", "/jira", "/confluence"]:
        assert client.get(route).status_code == 200, route

    key = "REQ-104"
    ticket = store.get_ticket(key)
    page = store.get_page(ticket["linked_page_id"])
    original_body = store.page_body(page)
    original_version = page["versions"][-1]["n"]
    print("First event: request an analysis of the seeded ticket.", flush=True)
    response = client.post(f"/jira/{key}/rerun", follow_redirects=True)
    assert response.status_code == 200
    first = store.runs_for_ticket(key)
    assert len(first) == 1
    assert store.page_body(store.get_page(page["id"])) == original_body

    print("Second event: edit the requirement; its open ticket retriggers automatically.", flush=True)
    amended_body = original_body + "\n\nEach uploaded file must be at most 20 MB."
    response = client.post(
        f"/confluence/{page['id']}/save",
        data={"body": amended_body, "author": store.PEOPLE[0]},
        follow_redirects=True,
    )
    assert response.status_code == 200
    runs = store.runs_for_ticket(key)
    assert len(runs) == 2
    updated_page = store.get_page(page["id"])
    assert updated_page["versions"][-1]["n"] == original_version + 1
    assert store.page_body(updated_page) == amended_body
    updated_ticket = store.get_ticket(key)
    assert updated_ticket["status"] == "Analysis Ready"
    assert updated_ticket["last_analyzed_version"] == original_version + 1
    assert sorted(run["report_version"] for run in runs) == [1, 2]

    record = {
        "exercise": "L5 Event-Driven Loop",
        "mode": "live",
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "ticket": key,
        "data_directory": str(data.relative_to(root)),
        "triggered_runs": len(runs),
        "requirement_versions": [run["requirement_version"] for run in runs],
        "report_versions": [run["report_version"] for run in runs],
        "verification_statuses": [run["status"] for run in runs],
        "final_ticket_status": updated_ticket["status"],
        "human_marked_done": False,
    }
    (root / "L5_practice_results.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    html = client.get(f"/jira/{key}").get_data(as_text=True)
    (root / "L5_ticket_after_events.html").write_text(html, encoding="utf-8")
    print(json.dumps(record, indent=2), flush=True)
    return record


if __name__ == "__main__":
    run_demo()
