import sqlite3
from flask import Flask, abort, jsonify, request, url_for, g
from werkzeug.exceptions import HTTPException

app = Flask(__name__)

ALLOWED_FIELDS = {'title', 'done'}

############ START OF DATABASE LAYER ######################
app.config["DATABASE"] = "tasks.db"

def get_db():
    if "db" not in g: #Open the connection only if it doesn't exist yet for this request
        g.db = sqlite3.connect(app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
    return g.db

@app.teardown_appcontext
def close_db(exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = get_db()
    db.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id    INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT    NOT NULL,
            done  INTEGER NOT NULL DEFAULT 0
        )
    """)
    db.commit()

with app.app_context():
    init_db()

def row_to_task(row):
    return {"id": row["id"], "title": row["title"], "done": bool(row["done"])}


def fetch_task(task_id):
    row = get_db().execute(
        "SELECT * FROM tasks WHERE id = ?", (task_id,)
    ).fetchone()
    if row is None:
        abort(404, description=f"Task {task_id} not found.")
    return row_to_task(row)
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
############# END VALIDATION AND ERROR HANDLING ######################


############ START OF HTTP METHODS ########################
@app.get("/tasks")
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


@app.get("/tasks/<int:task_id>")
def get_task(task_id):
    return jsonify(fetch_task(task_id))


@app.post("/tasks")
def create_task():
    data = validate_task(request.get_json(silent=True), required={"title"})
    db = get_db()
    cur = db.execute(
        "INSERT INTO tasks (title, done) VALUES (?, ?)",
        (data["title"], int(data.get("done", False))),
    )
    db.commit()
    task = fetch_task(cur.lastrowid)
    location = url_for("get_task", task_id=task["id"])
    return jsonify(task), 201, {"Location": location}


@app.delete("/tasks/<int:task_id>")
def delete_task(task_id):
    fetch_task(task_id)
    db = get_db()
    db.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
    db.commit()
    return "", 204


@app.put("/tasks/<int:task_id>")
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


@app.patch("/tasks/<int:task_id>")
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
############ END OF HTTP METHODS #################