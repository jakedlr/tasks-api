import pytest

from app import app, init_db


@pytest.fixture
def client(tmp_path):
    app.config.update(TESTING=True, DATABASE=str(tmp_path / "test.db"))
    with app.app_context():
        init_db()
    with app.test_client() as client:
        yield client


def test_create_then_get(client):
    resp = client.post("/tasks", json={"title": "Write tests"})
    assert resp.status_code == 201
    assert resp.get_json() == {"id": 1, "title": "Write tests", "done": False}
    assert resp.headers["Location"].endswith("/tasks/1")

    resp = client.get("/tasks/1")
    assert resp.status_code == 200
    assert resp.get_json()["title"] == "Write tests"


def test_missing_task_is_404_json(client):
    resp = client.get("/tasks/42")
    assert resp.status_code == 404
    assert resp.get_json()["error"] == "Not Found"


def test_validation_errors(client):
    assert client.post("/tasks", json={"title": ""}).status_code == 422
    assert client.post("/tasks", json={"title": "x", "color": "red"}).status_code == 422
    assert client.post("/tasks", json={"title": "x", "done": "maybe"}).status_code == 422
    assert client.post("/tasks", data="not json").status_code == 400


def test_put_requires_all_fields_but_patch_does_not(client):
    client.post("/tasks", json={"title": "Original"})
    assert client.put("/tasks/1", json={"title": "New"}).status_code == 422

    resp = client.patch("/tasks/1", json={"done": True})
    assert resp.status_code == 200
    assert resp.get_json() == {"id": 1, "title": "Original", "done": True}


def test_delete_then_404(client):
    client.post("/tasks", json={"title": "Temp"})
    assert client.delete("/tasks/1").status_code == 204
    assert client.delete("/tasks/1").status_code == 404
    assert client.get("/tasks/1").status_code == 404


def test_ids_are_not_reused(client):
    client.post("/tasks", json={"title": "A"})
    client.post("/tasks", json={"title": "B"})
    client.delete("/tasks/2")
    resp = client.post("/tasks", json={"title": "C"})
    assert resp.get_json()["id"] == 3


def test_filter_and_pagination(client):
    for i in range(5):
        client.post("/tasks", json={"title": f"t{i}", "done": i % 2 == 0})

    done = client.get("/tasks?done=true").get_json()
    assert [t["id"] for t in done] == [1, 3, 5]

    page = client.get("/tasks?limit=2&offset=2").get_json()
    assert [t["id"] for t in page] == [3, 4]