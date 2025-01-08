from flask import Flask, request, jsonify
from multiprocessing import Process, Manager
from threading import Thread, Lock
import uuid
from typing import List, Dict, Any, TypedDict, cast
from http import HTTPStatus


app = Flask(__name__)

MAX_NUMBER = 100


class ThreadResult(TypedDict):
    thread_id: int
    result: int


class ProcessResult(TypedDict):
    process_id: int
    threads: List[ThreadResult]
    process_sum: int


class TaskResult(TypedDict):
    status: str
    processes: List[ProcessResult]
    total_sum: int


# 프로세스 간 공유되는 결과 딕셔너리 타입
ResultDict = Dict[int, ProcessResult]

# 작업 정보를 저장하는 딕셔너리 타입
TasksDict = Dict[str, TaskResult]
# manager = Manager()
# result = cast(ResultDict, manager.dict())
# tasks = cast(TasksDict, manager.dict())
# lock = manager.Lock()


def perform_thread_task(
    thread_id: int,
    start: int,
    end: int,
    process_id: int,
    result: ResultDict,
    lock: Lock,
) -> None:

    thread_sum = sum(range(start, end + 1))
    with lock:
        process_data = result[process_id]
        process_data["threads"].append({"thread_id": thread_id, "result": thread_sum})
        process_data["process_sum"] += thread_sum
        result[process_id] = process_data

    return


def perform_process_task(
    process_id: int, num_threads: int, result: ResultDict, lock: Lock
) -> None:
    with lock:
        result[process_id] = {
            "process_id": process_id,
            "threads": [],
            "process_sum": 0,
        }

    step = MAX_NUMBER / num_threads
    threads: List[Thread] = []
    for thread_id in range(1, num_threads + 1):
        start = int((thread_id - 1) * step) + 1
        end = int(thread_id * step)
        if thread_id == num_threads:
            end = MAX_NUMBER
        thread = Thread(
            target=perform_thread_task,
            args=(thread_id, start, end, process_id, result, lock),
        )
        threads.append(thread)
        thread.start()

    for thread in threads:
        thread.join()

    with lock:
        result[process_id]["process_sum"] = sum(
            thread_info["result"] for thread_info in result[process_id]["threads"]
        )


@app.route("/process/start", methods=["POST"])
def start_process() -> Any:

    data = request.get_json()
    process_count = data.get("process_count")
    threads_per_process = data.get("threads_per_process")

    if not (1 <= process_count <= 4) or not (1 <= threads_per_process <= 100):
        return (
            jsonify(
                {
                    "error": "Invalid input. Process count (1-4) and threads per process (1-100) required."
                }
            ),
            HTTPStatus.BAD_REQUEST,
        )

    task_id = str(uuid.uuid4())

    processes: List[Process] = []

    for process_id in range(1, process_count + 1):
        process = Process(
            target=perform_process_task,
            args=(process_id, threads_per_process, result, lock),
        )
        processes.append(process)
        process.start()

    for process in processes:
        process.join()

    total_sum = sum(
        result[proc_id]["process_sum"]
        for proc_id in result
        if result[proc_id] is not None
    )
    tasks[task_id] = {
        "status": "completed",
        "processes": [
            result[proc_id] for proc_id in result if result[proc_id] is not None
        ],
        "total_sum": total_sum,
    }

    return jsonify({"status": "success", "task_id": task_id})


@app.route("/task/<task_id>", methods=["GET"])
def get_task(task_id: str) -> Any:

    task = tasks.get(task_id)
    if not task:
        return jsonify({"error": "Task not found."}), HTTPStatus.NOT_FOUND

    return jsonify(task)


if __name__ == "__main__":
    manager = Manager()
    result = cast(ResultDict, manager.dict())
    tasks = cast(TasksDict, manager.dict())
    lock = manager.Lock()
    app.run(debug=True)
