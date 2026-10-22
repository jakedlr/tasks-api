import sqlite3
from flask import Flask, abort, jsonify, request, url_for, g, Blueprint
from werkzeug.exceptions import HTTPException
import hmac
import os

app = Flask(__name__)
api = Blueprint("api", __name__, url_prefix="/v1")

ALLOWED_FIELDS = {'title', 'done'}

############ START OF DATABASE LAYER ######################
app.config["DATABASE"] = "tasks.db"
app.config["API_KEY"] = os.environ.get("TASKS_API_KEY", "dev-key")

def get_db():
    if "db" not in g: #Open the connection only if it doesn't exist yet for this request
        g.db = sqlite3.connect(app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON") #Necessary to connect tasks->projects
    return g.db

@app.teardown_appcontext
def close_db(exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = get_db()
    #TASKS TABLE
    db.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id    INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT    NOT NULL,
            done  INTEGER NOT NULL DEFAULT 0
        )
    """)
    #PROJECTS TABLE
    db.execute("""
        CREATE TABLE IF NOT EXISTS projects (
            id   INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT    NOT NULL UNIQUE
        )
    """)
    migrate_db(db)
    db.commit()


def migrate_db(db):
    columns = {row["name"] for row in db.execute("PRAGMA table_info(tasks)")}
    if "project_id" not in columns:
        db.execute(
            "ALTER TABLE tasks ADD COLUMN project_id INTEGER "
            "REFERENCES projects(id) ON DELETE CASCADE"
        )
with app.app_context():
    init_db()


def row_to_task(row):
    return {
        "id": row["id"], 
        "title": row["title"], 
        "done": bool(row["done"]),
        "project_id": row["project_id"], #Trailing comma intentional here; python ignores it
    }


def fetch_task(task_id):
    row = get_db().execute(
        "SELECT * FROM tasks WHERE id = ?", (task_id,)
    ).fetchone()
    if row is None:
        abort(404, description=f"Task {task_id} not found.")
    return row_to_task(row)


#Project Helpers
def row_to_project(row):
    return {"id": row["id"], "name": row["name"]}


def fetch_project(project_id):
    row = get_db().execute(
        "SELECT * FROM projects WHERE id = ?", (project_id,)
    ).fetchone()
    if row is None:
        abort(404, description=f"Project {project_id} not found.")
    return row_to_project(row)
############ END OF DATABASE LAYER #################


############ START VALIDATION AND ERROR HANDLING ##################
def validate_task(data, required):
    if not isinstance(data, dict):
        abort(400, description="Request body must be a JSON object.")
    unknown = set(data) - ALLOWED_FIELDS
    if unknown:
        abort(422, description=f"Unknown fields: {sorted(unknown)}")
    missing = set(required) - set(data)
    if missing:
        abort(422, description=f"Missing fields: {sorted(missing)}")
    if "title" in data:
        if not isinstance(data["title"], str) or not data["title"].strip():
            abort(422, description="'title' must be a non-empty string.")
        data["title"] = data["title"].strip()
    if "done" in data and not isinstance(data["done"], bool):
        abort(422, description="'done' must be true or false.")
    return data

#Fix ERROR 400, 401, 403, 404, 500, etc
#(Changes default Flask HTTP errors to JSON)
@app.errorhandler(HTTPException)
def handle_http_error(e):
    return jsonify(error=e.name, message=e.description), e.code

#Projects validation
def validate_project(data):
    if not isinstance(data, dict):
        abort(400, description="Request body must be a JSON object.")
    unknown = set(data) - {"name"}
    if unknown:
        abort(422, description=f"Unknown fields: {sorted(unknown)}")
    if "name" not in data:
        abort(422, description="Missing fields: ['name']")
    if not isinstance(data["name"], str) or not data["name"].strip():
        abort(422, description="'name' must be a non-empty string.")
    data["name"] = data["name"].strip()
    return data
############# END VALIDATION AND ERROR HANDLING ######################

############# START AUTH CHECK ###################
WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

@app.before_request
def require_api_key():
    if request.method not in WRITE_METHODS:
        return
    provided = request.headers.get("X-API-Key", "")
    expected = app.config["API_KEY"]
    if not hmac.compare_digest(provided.encode(), expected.encode()):
        abort(401, description="Missing or invalid API key.")
############# END AUTH CHECK #####################

############ START OF HTTP METHODS ########################
@api.get("/tasks")
def list_tasks():
    query = "SELECT * FROM tasks"
    params = []

    done = request.args.get("done")
    if done is not None:
        if done not in ("true", "false"):
            abort(400, description="'done' must be 'true' or 'false'.")
        query += " WHERE done = ?"
        params.append(1 if done == "true" else 0)

    limit = request.args.get("limit", default=20, type=int)
    offset = request.args.get("offset", default=0, type=int)
    limit = max(1, min(limit, 100))
    offset = max(0, offset)

    query += " ORDER BY id LIMIT ? OFFSET ?"
    params += [limit, offset]

    rows = get_db().execute(query, params).fetchall()
    return jsonify([row_to_task(r) for r in rows])


@api.get("/tasks/<int:task_id>")
def get_task(task_id):
    return jsonify(fetch_task(task_id))


@api.post("/tasks")
def create_task():
    data = validate_task(request.get_json(silent=True), required={"title"})
    db = get_db()
    cur = db.execute(
        "INSERT INTO tasks (title, done) VALUES (?, ?)",
        (data["title"], int(data.get("done", False))),
    )
    db.commit()
    task = fetch_task(cur.lastrowid)
    location = url_for("api.get_task", task_id=task["id"])
    return jsonify(task), 201, {"Location": location}


@api.delete("/tasks/<int:task_id>")
def delete_task(task_id):
    fetch_task(task_id)
    db = get_db()
    db.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
    db.commit()
    return "", 204


@api.put("/tasks/<int:task_id>")
def replace_task(task_id):
    fetch_task(task_id)
    data = validate_task(request.get_json(silent=True), required={"title", "done"})
    db = get_db()
    db.execute(
        "UPDATE tasks SET title = ?, done = ? WHERE id = ?",
        (data["title"], int(data["done"]), task_id),
    )
    db.commit()
    return jsonify(fetch_task(task_id))


@api.patch("/tasks/<int:task_id>")
def update_task(task_id):
    current = fetch_task(task_id)
    data = validate_task(request.get_json(silent=True), required=set())
    updated = {**current, **data}
    db = get_db()
    db.execute(
        "UPDATE tasks SET title = ?, done = ? WHERE id = ?",
        (updated["title"], int(updated["done"]), task_id),
    )
    db.commit()
    return jsonify(fetch_task(task_id))


#Project endpoints (part 14)
@api.get("/projects")
def list_projects():
    rows = get_db().execute("SELECT * FROM projects ORDER BY id").fetchall()
    return jsonify([row_to_project(r) for r in rows])


@api.get("/projects/<int:project_id>")
def get_project(project_id):
    return jsonify(fetch_project(project_id))


@api.post("/projects")
def create_project():
    data = validate_project(request.get_json(silent=True))
    db = get_db()
    try:
        cur = db.execute("INSERT INTO projects (name) VALUES (?)", (data["name"],))
        db.commit()
    except sqlite3.IntegrityError:
        db.rollback()
        abort(409, description=f"A project named '{data['name']}' already exists.")
    project = fetch_project(cur.lastrowid)
    location = url_for("api.get_project", project_id=project["id"])
    return jsonify(project), 201, {"Location": location}


@api.delete("/projects/<int:project_id>")
def delete_project(project_id):
    fetch_project(project_id)
    db = get_db()
    db.execute("DELETE FROM projects WHERE id = ?", (project_id,))
    db.commit()
    return "", 204


#Part 15 (linking projects to tasks)
@api.get("/projects/<int:project_id>/tasks")
def list_project_tasks(project_id):
    fetch_project(project_id)
    rows = get_db().execute(
        "SELECT * FROM tasks WHERE project_id = ? ORDER BY id", (project_id,)
    ).fetchall()
    return jsonify([row_to_task(r) for r in rows])


@api.post("/projects/<int:project_id>/tasks")
def create_project_task(project_id):
    fetch_project(project_id)
    data = validate_task(request.get_json(silent=True), required={"title"})
    db = get_db()
    cur = db.execute(
        "INSERT INTO tasks (title, done, project_id) VALUES (?, ?, ?)",
        (data["title"], int(data.get("done", False)), project_id),
    )
    db.commit()
    task = fetch_task(cur.lastrowid)
    location = url_for("api.get_task", task_id=task["id"])
    return jsonify(task), 201, {"Location": location}
############ END OF HTTP METHODS #################

#Register the Blueprint
app.register_blueprint(api)