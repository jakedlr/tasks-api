import pytest

from app import app, init_db


@pytest.fixture
def client(tmp_path):
    app.config.update(
        TESTING=True,
        DATABASE=str(tmp_path / "test.db"),
        API_KEY="test-key",
    )
    with app.app_context():
        init_db()
    with app.test_client() as client:
        client.environ_base["HTTP_X_API_KEY"] = "test-key"
        yield client


def test_create_then_get(client):
    resp = client.post("/v1/tasks", json={"title": "Write tests"})
    assert resp.status_code == 201
    assert resp.get_json() == {"id": 1, "title": "Write tests", "done": False, "project_id": None}
    assert resp.headers["Location"].endswith("/v1/tasks/1")

    resp = client.get("/v1/tasks/1")
    assert resp.status_code == 200
    assert resp.get_json()["title"] == "Write tests"


def test_missing_task_is_404_json(client):
    resp = client.get("/v1/tasks/42")
    assert resp.status_code == 404
    assert resp.get_json()["error"] == "Not Found"


def test_validation_errors(client):
    assert client.post("/v1/tasks", json={"title": ""}).status_code == 422
    assert client.post("/v1/tasks", json={"title": "x", "color": "red"}).status_code == 422
    assert client.post("/v1/tasks", json={"title": "x", "done": "maybe"}).status_code == 422
    assert client.post("/v1/tasks", data="not json").status_code == 400


def test_put_requires_all_fields_but_patch_does_not(client):
    client.post("/v1/tasks", json={"title": "Original"})
    assert client.put("/v1/tasks/1", json={"title": "New"}).status_code == 422

    resp = client.patch("/v1/tasks/1", json={"done": True})
    assert resp.status_code == 200
    assert resp.get_json() == {"id": 1, "title": "Original", "done": True, "project_id": None}


def test_delete_then_404(client):
    client.post("/v1/tasks", json={"title": "Temp"})
    assert client.delete("/v1/tasks/1").status_code == 204
    assert client.delete("/v1/tasks/1").status_code == 404
    assert client.get("/v1/tasks/1").status_code == 404


def test_ids_are_not_reused(client):
    client.post("/v1/tasks", json={"title": "A"})
    client.post("/v1/tasks", json={"title": "B"})
    client.delete("/v1/tasks/2")
    resp = client.post("/v1/tasks", json={"title": "C"})
    assert resp.get_json()["id"] == 3


def test_filter_and_pagination(client):
    for i in range(5):
        client.post("/v1/tasks", json={"title": f"t{i}", "done": i % 2 == 0})

    done = client.get("/v1/tasks?done=true").get_json()
    assert [t["id"] for t in done] == [1, 3, 5]

    page = client.get("/v1/tasks?limit=2&offset=2").get_json()
    assert [t["id"] for t in page] == [3, 4]

# AUTH TESTS

def test_writes_require_api_key(client):
    anon = app.test_client()
    resp = anon.post("/v1/tasks", json={"title": "x"})
    assert resp.status_code == 401
    assert resp.get_json()["error"] == "Unauthorized"

    resp = anon.post("/v1/tasks", json={"title": "x"}, headers={"X-API-Key": "wrong"})
    assert resp.status_code == 401
    assert anon.get("/v1/tasks").get_json() == []


def test_reads_do_not_require_api_key(client):
    client.post("/v1/tasks", json={"title": "Public"})
    anon = app.test_client()
    assert anon.get("/v1/tasks").status_code == 200
    assert anon.get("/v1/tasks/1").status_code == 200


def test_unversioned_path_is_404(client):
    resp = client.get("/tasks")
    assert resp.status_code == 404
    assert resp.get_json()["error"] == "Not Found"


#Part 14 tests
def test_create_and_get_project(client):
    resp = client.post("/v1/projects", json={"name": "Home"})
    assert resp.status_code == 201
    assert resp.get_json() == {"id": 1, "name": "Home"}
    assert resp.headers["Location"].endswith("/v1/projects/1")
    assert client.get("/v1/projects/1").get_json()["name"] == "Home"


def test_duplicate_project_name_is_409(client):
    client.post("/v1/projects", json={"name": "Home"})
    resp = client.post("/v1/projects", json={"name": "  Home  "})
    assert resp.status_code == 409
    assert resp.get_json()["error"] == "Conflict"


def test_project_validation_and_404(client):
    assert client.post("/v1/projects", json={}).status_code == 422
    assert client.post("/v1/projects", json={"name": "x", "color": "red"}).status_code == 422
    assert client.get("/v1/projects/99").status_code == 404


def test_delete_project(client):
    client.post("/v1/projects", json={"name": "Temp"})
    assert client.delete("/v1/projects/1").status_code == 204
    assert client.get("/v1/projects/1").status_code == 404


#Part 15 tests
def test_nested_task_creation_and_listing(client):
    client.post("/v1/projects", json={"name": "Home"})
    resp = client.post("/v1/projects/1/tasks", json={"title": "Dishes"})
    assert resp.status_code == 201
    assert resp.get_json()["project_id"] == 1
    assert resp.headers["Location"].endswith("/v1/tasks/1")

    client.post("/v1/tasks", json={"title": "Unassigned"})
    tasks = client.get("/v1/projects/1/tasks").get_json()
    assert [t["title"] for t in tasks] == ["Dishes"]


def test_empty_project_returns_empty_list(client):
    client.post("/v1/projects", json={"name": "Empty"})
    resp = client.get("/v1/projects/1/tasks")
    assert resp.status_code == 200
    assert resp.get_json() == []


def test_nested_routes_404_for_missing_project(client):
    assert client.get("/v1/projects/99/tasks").status_code == 404
    assert client.post("/v1/projects/99/tasks", json={"title": "x"}).status_code == 404


def test_deleting_project_cascades_to_its_tasks(client):
    client.post("/v1/projects", json={"name": "Home"})
    client.post("/v1/projects/1/tasks", json={"title": "Dishes"})
    client.post("/v1/tasks", json={"title": "Unassigned"})
    client.delete("/v1/projects/1")
    assert client.get("/v1/tasks/1").status_code == 404
    assert client.get("/v1/tasks/2").status_code == 200