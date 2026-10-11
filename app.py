from flask import Flask, abort, jsonify

app = Flask(__name__)

tasks = {
    1: {"id": 1, "title": "Learn REST", "done": False},
    2: {"id": 2, "title": "Learn Flask", "done": False},
}


@app.get("/tasks")
def list_tasks():
    return jsonify(list(tasks.values()))


@app.get("/tasks/<int:task_id>")
def get_task(task_id):
    task = tasks.get(task_id)
    if task is None:
        abort(404)
    return jsonify(task)