from itertools import count
from flask import Flask, abort, jsonify, request, url_for

app = Flask(__name__)

tasks = {
    1: {"id": 1, "title": "Learn REST", "done": False},
    2: {"id": 2, "title": "Learn Flask", "done": False},
}

id_counter = count(start=max(tasks) + 1) #Iterator to track where we are as we POST

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
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or "title" not in data:
        abort(400)
    task_id = next(id_counter)
    task = {"id": task_id, "title": data["title"], "done": False}
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
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or "title" not in data or "done" not in data:
        abort(400)
    task = {"id": task_id, "title": data["title"], "done": data["done"]}
    tasks[task_id] = task
    return jsonify(task)


@app.patch("/tasks/<int:task_id>")
def update_task(task_id):
    if task_id not in tasks:
        abort(404)
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        abort(400)
    task = tasks[task_id]
    if "title" in data:
        task["title"] = data["title"]
    if "done" in data:
        task["done"] = data["done"]
    return jsonify(task)