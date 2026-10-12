from itertools import count
from flask import Flask, abort, jsonify, request, url_for
from werkzeug.exceptions import HTTPException

app = Flask(__name__)

tasks = {
    1: {"id": 1, "title": "Learn REST", "done": False},
    2: {"id": 2, "title": "Learn Flask", "done": False},
}

id_counter = count(start=max(tasks) + 1) #Iterator to track where we are as we POST
ALLOWED_FIELDS = {'title', 'done'}

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

@app.get("/tasks")
def list_tasks():
    return jsonify(list(tasks.values()))


@app.get("/tasks/<int:task_id>")
def get_task(task_id):
    task = tasks.get(task_id)
    if task is None:
        abort(404)
    return jsonify(task)


@app.post("/tasks")
def create_task():
    data = validate_task(request.get_json(silent=True), required={"title"})
    task_id = next(id_counter)
    task = {"id": task_id, "title": data["title"], "done": data.get("done", False)}
    tasks[task_id] = task
    location = url_for("get_task", task_id=task_id)
    return jsonify(task), 201, {"Location": location}


@app.delete("/tasks/<int:task_id>")
def delete_task(task_id):
    if task_id not in tasks:
        abort(404)
    del tasks[task_id]
    return "", 204


@app.put("/tasks/<int:task_id>")
def replace_task(task_id):
    if task_id not in tasks:
        abort(404)
    data = validate_task(request.get_json(silent=True), required={"title", "done"})
    task = {"id": task_id, "title": data["title"], "done": data["done"]}
    tasks[task_id] = task
    return jsonify(task)


@app.patch("/tasks/<int:task_id>")
def update_task(task_id):
    if task_id not in tasks:
        abort(404)
    data = validate_task(request.get_json(silent=True), required=set())
    task = tasks[task_id]
    if "title" in data:
        task["title"] = data["title"]
    if "done" in data:
        task["done"] = data["done"]
    return jsonify(task)