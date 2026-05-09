"""
Intelligent Auto-Grading System — Flask Backend
"""

import os, sys, json, time, uuid, subprocess, threading, difflib, re, csv, io
from flask import Flask, request, jsonify, send_from_directory, Response
from werkzeug.utils import secure_filename

app = Flask(__name__, static_folder="static")
app.config["UPLOAD_FOLDER"] = os.path.join(os.path.dirname(__file__), "uploads")
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024  # 5MB

os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

ALLOWED = {".py"}
TIMEOUT = 5  # seconds per execution

# ── In-memory result store ──────────────────────────────────────────────────
results_store: dict[str, dict] = {}


# ── Helpers ─────────────────────────────────────────────────────────────────

def allowed(filename: str) -> bool:
    return os.path.splitext(filename)[1].lower() in ALLOWED


def normalize(text: str) -> str:
    """Strip and normalize whitespace for comparison."""
    lines = [l.rstrip() for l in text.strip().splitlines()]
    return "\n".join(lines)


def similarity_score(a: str, b: str) -> float:
    """Return 0–1 similarity ratio."""
    return difflib.SequenceMatcher(None, normalize(a), normalize(b)).ratio()


def execute_code(filepath: str, stdin_data: str = "", timeout: int = TIMEOUT) -> dict:
    """
    Safely execute a Python file in a subprocess.
    Returns dict with stdout, stderr, exit_code, exec_time.
    """
    start = time.perf_counter()
    try:
        result = subprocess.run(
            [sys.executable, filepath],
            input=stdin_data,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        elapsed = round((time.perf_counter() - start) * 1000, 2)
        return {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "exit_code": result.returncode,
            "exec_time_ms": elapsed,
            "timed_out": False,
        }
    except subprocess.TimeoutExpired:
        elapsed = round((time.perf_counter() - start) * 1000, 2)
        return {
            "stdout": "",
            "stderr": f"Execution timed out after {timeout}s",
            "exit_code": -1,
            "exec_time_ms": elapsed,
            "timed_out": True,
        }
    except Exception as e:
        return {
            "stdout": "",
            "stderr": str(e),
            "exit_code": -1,
            "exec_time_ms": 0,
            "timed_out": False,
        }


def categorize_error(stderr: str) -> str:
    if not stderr:
        return "none"
    if "SyntaxError" in stderr or "IndentationError" in stderr:
        return "syntax"
    if "TimeoutExpired" in stderr or "timed out" in stderr.lower():
        return "timeout"
    return "runtime"


def grade_result(student_out: str, expected_out: str, test_cases: list) -> dict:
    """
    Evaluate output and return marks (0–100).
    Supports single expected output or multi-test-case.
    """
    if test_cases:
        passed = sum(
            1 for tc in test_cases
            if normalize(tc.get("actual", "")) == normalize(tc.get("expected", ""))
        )
        total = len(test_cases)
        marks = round((passed / total) * 100) if total else 0
        return {"marks": marks, "passed_tests": passed, "total_tests": total}

    sim = similarity_score(student_out, expected_out)
    if normalize(student_out) == normalize(expected_out):
        marks = 100
    elif sim >= 0.85:
        marks = 75
    elif sim >= 0.60:
        marks = 50
    else:
        marks = 0

    return {"marks": marks, "similarity": round(sim * 100, 1), "passed_tests": None, "total_tests": None}


# ── Routes ───────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return send_from_directory("static", "index.html")


@app.route("/api/grade", methods=["POST"])
def grade():
    """
    Expects multipart form:
      - files[]:  one or more .py files
      - expected: (optional) expected output text
      - test_inputs: (optional) JSON array of {input, expected} objects
      - marks_per_file: (optional) int, default 100
    """
    uploaded = request.files.getlist("files[]")
    expected_raw = request.form.get("expected", "").strip()
    test_inputs_raw = request.form.get("test_inputs", "[]")
    marks_total = int(request.form.get("marks_per_file", 100))

    try:
        test_cases_def = json.loads(test_inputs_raw)
    except Exception:
        test_cases_def = []

    if not uploaded:
        return jsonify({"error": "No files uploaded"}), 400

    session_id = str(uuid.uuid4())[:8]
    file_results = []

    for f in uploaded:
        if not f or not f.filename:
            continue
        if not allowed(f.filename):
            file_results.append({
                "filename": f.filename,
                "status": "error",
                "error_type": "invalid_file",
                "stderr": "Not a .py file",
                "stdout": "",
                "expected": expected_raw,
                "marks": 0,
                "exec_time_ms": 0,
                "similarity": 0,
                "passed_tests": None,
                "total_tests": None,
            })
            continue

        safe = secure_filename(f.filename)
        fpath = os.path.join(app.config["UPLOAD_FOLDER"], f"{session_id}_{safe}")
        f.save(fpath)

        try:
            # Run with/without test cases
            if test_cases_def:
                tc_results = []
                total_time = 0
                for tc in test_cases_def:
                    run = execute_code(fpath, stdin_data=str(tc.get("input", "")))
                    total_time += run["exec_time_ms"]
                    tc_results.append({
                        "input": tc.get("input", ""),
                        "expected": tc.get("expected", ""),
                        "actual": run["stdout"],
                        "passed": normalize(run["stdout"]) == normalize(tc.get("expected", "")),
                    })

                grading = grade_result("", "", tc_results)
                first_run = execute_code(fpath)
                stderr = first_run["stderr"]
                stdout = "\n".join(
                    f"[Test {i+1}] {'✓' if r['passed'] else '✗'} → {repr(r['actual'].strip())}"
                    for i, r in enumerate(tc_results)
                )
                exec_time = round(total_time / len(test_cases_def), 2)
            else:
                run = execute_code(fpath)
                stderr = run["stderr"]
                stdout = run["stdout"]
                exec_time = run["exec_time_ms"]
                grading = grade_result(stdout, expected_raw, [])

            error_type = categorize_error(stderr)
            if stderr and grading["marks"] == 0:
                status = "error"
            elif grading["marks"] == 100:
                status = "pass"
            elif grading["marks"] > 0:
                status = "partial"
            else:
                status = "fail"

            # Scale to marks_total
            final_marks = round((grading["marks"] / 100) * marks_total, 1)

            file_results.append({
                "filename": f.filename,
                "status": status,
                "error_type": error_type,
                "stderr": stderr,
                "stdout": stdout,
                "expected": expected_raw,
                "marks": final_marks,
                "max_marks": marks_total,
                "exec_time_ms": exec_time,
                "similarity": grading.get("similarity", 0),
                "passed_tests": grading.get("passed_tests"),
                "total_tests": grading.get("total_tests"),
            })
        finally:
            try:
                os.remove(fpath)
            except Exception:
                pass

    # Sort for leaderboard
    file_results.sort(key=lambda x: -x["marks"])
    for i, r in enumerate(file_results):
        r["rank"] = i + 1

    results_store[session_id] = file_results
    return jsonify({"session_id": session_id, "results": file_results})


@app.route("/api/export/<session_id>")
def export_csv(session_id):
    data = results_store.get(session_id)
    if not data:
        return jsonify({"error": "Session not found"}), 404

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=[
        "rank", "filename", "status", "marks", "max_marks",
        "exec_time_ms", "similarity", "passed_tests", "total_tests", "error_type"
    ])
    writer.writeheader()
    for r in data:
        writer.writerow({k: r.get(k, "") for k in writer.fieldnames})

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename=grades_{session_id}.csv"}
    )


if __name__ == "__main__":
    print("🎓 Auto-Grader running → http://localhost:5000")
    app.run(debug=True, port=5000)
