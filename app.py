import os
import random
import json
import sys
from datetime import datetime

from flask import Flask, jsonify, request, send_file, render_template

# Allow importing from question_bank
sys.path.insert(0, r".")

from adaptive_engine import get_next_question
from tutor_engine import get_hint, get_next_hint
from gamification import ensure_table, update_gamification, get_gamification, get_leaderboard
from misconception_engine import detect_misconceptions
from ai_orchestrator import smart_pipeline

app = Flask(__name__)

PAPERS_DIR = r"D:\S1\_generated_papers\pdf"
BANK_PATH = r".\FINAL_MEGA_BANK.json"


def get_db():
    import psycopg2
    conn = psycopg2.connect(
        host="localhost", dbname="question_bank",
        user="postgres", password=""
    )
    ensure_table(conn)
    return conn



@app.route("/")
def landing():
    return app.send_static_file("landing.html") if __import__("os").path.exists(__import__("os").path.join(app.static_folder or "templates", "landing.html")) else "HK Math API Server"

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/topics")
def api_topics():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT topic FROM questions ORDER BY topic")
    topics = [row[0] for row in cur.fetchall()]
    cur.close()
    conn.close()
    return jsonify(topics)


@app.route("/api/questions")
def api_questions():
    topic = request.args.get("topic", "")
    limit = min(int(request.args.get("limit", 5)), 20)
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, question_text, answer, topic, difficulty, question_type, marks "
        "FROM questions WHERE topic = %s ORDER BY RANDOM() LIMIT %s",
        (topic, limit),
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return jsonify([
        {
            "id": r[0],
            "question_text": r[1],
            "answer": r[2],
            "topic": r[3],
            "difficulty": r[4],
            "question_type": r[5],
            "marks": r[6],
        }
        for r in rows
    ])


@app.route("/api/papers")
def api_papers():
    papers = []
    if os.path.isdir(PAPERS_DIR):
        for f in sorted(os.listdir(PAPERS_DIR)):
            if f.lower().endswith(".pdf"):
                path = os.path.join(PAPERS_DIR, f)
                papers.append({
                    "filename": f,
                    "size": os.path.getsize(path),
                })
    return jsonify(papers)


@app.route("/papers/<path:filename>")
def download_paper(filename):
    path = os.path.join(PAPERS_DIR, os.path.basename(filename))
    if not os.path.isfile(path):
        return jsonify({"error": "not found"}), 404
    return send_file(path, as_attachment=True, download_name=os.path.basename(path))


@app.route("/teacher")
def teacher_dashboard():
    return render_template("teacher.html")


@app.route("/api/teacher/stats")
def api_teacher_stats():
    conn = get_db()
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM questions")
    total = cur.fetchone()[0]

    cur.execute("SELECT topic, COUNT(*) FROM questions GROUP BY topic ORDER BY topic")
    topic_stats = [{"topic": r[0], "count": r[1]} for r in cur.fetchall()]

    cur.execute("SELECT form, COUNT(*) FROM questions GROUP BY form ORDER BY form")
    form_stats = [{"form": r[0] if r[0] != "" else "(empty)", "count": r[1]} for r in cur.fetchall()]

    cur.close()
    conn.close()
    return jsonify({"total": total, "by_topic": topic_stats, "by_form": form_stats})


@app.route("/api/teacher/questions")
def api_teacher_questions():
    topic = request.args.get("topic", "")
    conn = get_db()
    cur = conn.cursor()
    if topic:
        cur.execute(
            "SELECT id, question_text, answer, topic, form, difficulty, question_type, marks "
            "FROM questions WHERE topic = %s ORDER BY id LIMIT 100",
            (topic,),
        )
    else:
        cur.execute(
            "SELECT id, question_text, answer, topic, form, difficulty, question_type, marks "
            "FROM questions ORDER BY id LIMIT 100"
        )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return jsonify([
        {
            "id": r[0], "question_text": r[1], "answer": r[2],
            "topic": r[3], "form": r[4], "difficulty": r[5],
            "question_type": r[6], "marks": r[7],
        }
        for r in rows
    ])


@app.route("/api/teacher/paper/generate", methods=["POST"])
def api_teacher_paper_generate():
    data = request.get_json()
    topic = data.get("topic", "")
    form = data.get("form", "")
    difficulty = data.get("difficulty", "")
    num_questions = min(int(data.get("num_questions", 10)), 50)

    conn = get_db()
    cur = conn.cursor()
    conditions = []
    params = []
    if topic:
        conditions.append("topic = %s")
        params.append(topic)
    if form:
        conditions.append("form = %s")
        params.append(form)
    if difficulty:
        conditions.append("difficulty = %s")
        params.append(difficulty)

    where = "WHERE " + " AND ".join(conditions) if conditions else ""
    cur.execute(
        f"SELECT id, question_text, answer, topic, form, difficulty, question_type, marks "
        f"FROM questions {where} ORDER BY RANDOM() LIMIT %s",
        params + [num_questions],
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()

    if not rows:
        return jsonify({"error": "No questions matched"}), 404

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    topic_slug = topic.replace(" ", "_").replace(".", "")[:30] if topic else "all"
    filename = f"paper_{topic_slug}_f{form or 'all'}_d{difficulty or 'all'}_{ts}.pdf"
    filepath = os.path.join(PAPERS_DIR, filename)

    from fpdf import FPDF
    pdf = FPDF()
    pdf.add_page()
    pdf.add_font("HK", "", r"C:\Windows\Fonts\simhei.ttf", uni=True)
    pdf.add_font("HK", "B", r"C:\Windows\Fonts\simhei.ttf", uni=True)
    pdf.set_font("HK", "B", 14)
    pdf.cell(0, 10, "霖楓學苑 — 模擬試卷", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.set_font("HK", "", 10)
    pdf.cell(0, 8, f"Topic: {topic or 'All'} | Form: {form or 'All'} | Difficulty: {difficulty or 'All'}", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.cell(0, 8, f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')} | Questions: {len(rows)}", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.ln(6)

    for i, r in enumerate(rows):
        qid, qtext, answer, qtopic, qform, qdiff, qtype, qmarks = r
        pdf.set_font("HK", "B", 10)
        pdf.cell(0, 7, f"Q{i+1}. [{qtype or 'N/A'}] [{qmarks or 0} marks]  ({qdiff or 'N/A'})", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("HK", "", 10)
        pdf.multi_cell(0, 6, qtext)
        pdf.ln(2)

    pdf.add_page()
    pdf.set_font("HK", "B", 14)
    pdf.cell(0, 10, "Answer Key", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.ln(4)
    for i, r in enumerate(rows):
        qid, qtext, answer, qtopic, qform, qdiff, qtype, qmarks = r
        pdf.set_font("HK", "B", 9)
        pdf.cell(0, 6, f"Q{i+1}: ", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("HK", "", 9)
        pdf.multi_cell(0, 6, answer or "(no answer)")
        pdf.ln(1)

    os.makedirs(PAPERS_DIR, exist_ok=True)
    pdf.output(filepath)
    return jsonify({"filename": filename, "path": filepath, "questions": len(rows)})


# -- Bank index lookup (DB question_text -> JSON bank 0-based index) --
_bank_index_cache: dict[str, int] = {}


def _get_bank_index(question_text: str) -> int:
    """Find the 0-based index of a question in the JSON bank by matching text."""
    if not question_text:
        return -1
    key = question_text.strip()
    if key in _bank_index_cache:
        return _bank_index_cache[key]

    with open(BANK_PATH, "r", encoding="utf-8") as f:
        bank = json.load(f)["questions"]

    # Exact match
    for i, q in enumerate(bank):
        if (q.get("question") or "").strip() == key:
            _bank_index_cache[key] = i
            return i

    # Normalised match (collapse whitespace)
    import re
    def _norm(s):
        return re.sub(r"\s+", " ", (s or "").strip())

    nkey = _norm(key)
    for i, q in enumerate(bank):
        if _norm(q.get("question") or "") == nkey:
            _bank_index_cache[key] = i
            return i

    return -1


# ===== Progress / Submit endpoints =====


@app.route("/api/submit", methods=["POST"])
def api_submit():
    data = request.get_json()
    student_name = (data.get("student_name") or "").strip()
    question_id = data.get("question_id")
    answer = data.get("answer") or ""
    is_daily = data.get("is_daily", False)

    if not student_name:
        return jsonify({"error": "student_name is required"}), 400
    if question_id is None:
        return jsonify({"error": "question_id is required"}), 400

    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, question_text, topic FROM questions WHERE id = %s",
        (question_id,),
    )
    row = cur.fetchone()
    if not row:
        cur.close()
        conn.close()
        return jsonify({"error": "question not found"}), 404

    db_id, db_qtext, db_topic = row
    cur.close()
    conn.close()

    bank_idx = _get_bank_index(db_qtext)

    if bank_idx >= 0:
        from mark_engine import mark_with_feedback
        result = mark_with_feedback(answer, bank_idx)
    else:
        # Fallback: simple string match when bank lookup fails
        from mark_engine import mark_answer
        mr = mark_answer(answer, 0)  # won't work well, use fallback
        result = {
            "score": 0,
            "max_score": 1,
            "confidence": 0.0,
            "details": {"error": "bank index not found"},
            "status": "REVIEW",
            "score_display": "0/1",
            "message": "Answer submitted for review.",
            "hint": "",
            "related_topics": [],
            "suggested_practice": [],
        }

    # Write to student_progress
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO student_progress (student_name, question_id, score, max_score, status, topic)
           VALUES (%s, %s, %s, %s, %s, %s)""",
        (student_name, question_id, result["score"], result["max_score"],
         result["status"], db_topic or ""),
    )
    conn.commit()
    cur.close()
    conn.close()

    # Update gamification
    gconn = get_db()
    try:
        gdata = update_gamification(gconn, student_name, result["score"],
                                     result["max_score"], result["status"], is_daily)
    finally:
        gconn.close()

    result["gamification"] = gdata
    return jsonify(result)


@app.route("/api/progress/<student_name>")
def api_progress(student_name):
    conn = get_db()
    cur = conn.cursor()

    cur.execute(
        """SELECT COUNT(*), COALESCE(SUM(score),0), COALESCE(SUM(max_score),0)
           FROM student_progress WHERE student_name = %s""",
        (student_name,),
    )
    total, sum_score, sum_max = cur.fetchone()

    cur.execute(
        """SELECT status, COUNT(*) FROM student_progress
           WHERE student_name = %s GROUP BY status""",
        (student_name,),
    )
    by_status = {row[0]: row[1] for row in cur.fetchall()}

    cur.close()
    conn.close()

    avg_pct = round((sum_score / sum_max * 100), 1) if sum_max else 0

    return jsonify({
        "student_name": student_name,
        "total_questions": total,
        "total_score": round(sum_score, 2),
        "total_max": round(sum_max, 2),
        "average_pct": avg_pct,
        "by_status": by_status,
    })


@app.route("/api/progress/<student_name>/topics")
def api_progress_topics(student_name):
    conn = get_db()
    cur = conn.cursor()

    cur.execute(
        """SELECT topic, COUNT(*), COALESCE(SUM(score),0), COALESCE(SUM(max_score),0)
           FROM student_progress WHERE student_name = %s
           GROUP BY topic ORDER BY topic""",
        (student_name,),
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()

    topics = []
    for topic, cnt, sum_score, sum_max in rows:
        mastery = round((sum_score / sum_max * 100), 1) if sum_max else 0
        topics.append({
            "topic": topic,
            "count": cnt,
            "total_score": round(sum_score, 2),
            "total_max": round(sum_max, 2),
            "mastery_pct": mastery,
        })

    return jsonify(topics)


# ===== Adaptive Learning Engine =====


@app.route("/api/adaptive/<student_name>")
def api_adaptive(student_name):
    conn = get_db()
    try:
        qid, weak_topic = get_next_question(student_name, conn)
        return jsonify({"question_id": qid, "weak_topic": weak_topic, "status": "ok"})
    finally:
        conn.close()


@app.route("/api/adaptive/next")
def api_adaptive_next():
    student_name = (request.args.get("student_name") or "").strip()
    if not student_name:
        return jsonify({"error": "student_name is required"}), 400

    conn = get_db()
    try:
        qid, weak_topic = get_next_question(student_name, conn)
        return jsonify({"question_id": qid, "weak_topic": weak_topic, "status": "ok"})
    finally:
        conn.close()


# ===== Tutor Engine =====


@app.route("/api/tutor/solution/<int:question_id>")
def api_tutor_solution(question_id):
    """Return a step-by-step solution for a question (by DB id)."""
    from tutor_engine import generate_solution_for_db
    result = generate_solution_for_db(question_id)
    if "error" in result:
        return jsonify(result), 404
    return jsonify(result)


@app.route("/api/tutor/hint")
def api_tutor_hint():
    """Generate a Socratic hint for a student's wrong answer.

    Query params: question_id (required), student_answer (required)
    Returns: {question_id, topic, error_type, hint, student_answer}
    """
    from tutor_engine import generate_hint_for_db
    question_id = request.args.get("question_id", "")
    student_answer = request.args.get("student_answer", "")

    if not question_id:
        return jsonify({"error": "question_id is required"}), 400
    if not student_answer:
        return jsonify({"error": "student_answer is required"}), 400

    try:
        qid = int(question_id)
    except ValueError:
        return jsonify({"error": "question_id must be an integer"}), 400

    result = generate_hint_for_db(qid, student_answer)
    if "error" in result:
        return jsonify(result), 404
    return jsonify(result)


# ===== Gamification Engine =====


@app.route("/api/gamification/<student_name>")
def api_gamification(student_name):
    conn = get_db()
    try:
        data = get_gamification(conn, student_name)
        if not data:
            return jsonify({"student_name": student_name, "points": 0,
                            "streak": 0, "badge": "Bronze"})
        return jsonify(data)
    finally:
        conn.close()


@app.route("/api/gamification/leaderboard")
def api_leaderboard():
    conn = get_db()
    try:
        board = get_leaderboard(conn, limit=10)
        return jsonify(board)
    finally:
        conn.close()


@app.route("/api/gamification/daily", methods=["POST"])
def api_daily_challenge():
    data = request.get_json() or {}
    student_name = (data.get("student_name") or "").strip()
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute(
            """SELECT id, question_text, answer, topic, difficulty, question_type, marks
               FROM questions ORDER BY RANDOM() LIMIT 5"""
        )
        rows = cur.fetchall()
        cur.close()
        questions = [
            {
                "id": r[0], "question_text": r[1], "answer": r[2],
                "topic": r[3], "difficulty": r[4],
                "question_type": r[5], "marks": r[6],
            }
            for r in rows
        ]
        # Get current daily progress
        gdata = get_gamification(conn, student_name) or {}
        return jsonify({
            "questions": questions,
            "daily_correct": gdata.get("daily_correct", 0),
            "daily_target": 5,
            "daily_bonus_claimed": gdata.get("daily_bonus_claimed", False),
        })
    finally:
        conn.close()



# ===== Tutor Engine =====

@app.route("/api/tutor/hint", methods=["POST"])
def tutor_hint():
    data = request.get_json()
    question_id = data.get("question_id")
    student_answer = data.get("student_answer", "")
    conn = get_db()
    try:
        result, is_correct = get_hint(question_id, student_answer, conn)
        return jsonify(result)
    finally:
        conn.close()

@app.route("/api/tutor/next-hint")
def tutor_next_hint():
    question_id = request.args.get("question_id", type=int)
    hint_level = request.args.get("hint_level", 1, type=int)
    conn = get_db()
    try:
        result = get_next_hint(question_id, hint_level, conn)
        return jsonify(result)
    finally:
        conn.close()


# ===== Marking & Feedback Engine =====

import sys
sys.path.insert(0, r".")
from mark_engine import mark_answer, mark_with_feedback

@app.route("/api/mark", methods=["POST"])
def mark_answer_api():
    """Grade a student answer. POST {question_id, student_answer}"""
    data = request.get_json()
    question_id = data.get("question_id")
    student_answer = data.get("student_answer", "")
    if not question_id:
        return jsonify({"error": "question_id required"}), 400
    
    result = mark_with_feedback(student_answer, int(question_id))
    return jsonify(result)

@app.route("/api/feedback", methods=["POST"])
def feedback_api():
    """Get detailed feedback on an answer. POST {question_id, student_answer}"""
    data = request.get_json()
    question_id = data.get("question_id")
    student_answer = data.get("student_answer", "")
    if not question_id:
        return jsonify({"error": "question_id required"}), 400
    
    result = mark_with_feedback(student_answer, int(question_id))
    return jsonify({
        "score": result.get("score", 0),
        "is_correct": result.get("match_type", "") == "exact",
        "match_type": result.get("match_type", "unknown"),
        "feedback": result.get("feedback", ""),
        "steps": result.get("steps", [])
    })

@app.route("/api/submit", methods=["POST"])
def submit_answer_api():
    """Submit answer + record progress. POST {student_name, question_id, student_answer}"""
    data = request.get_json()
    student_name = data.get("student_name", "anonymous")
    question_id = data.get("question_id")
    student_answer = data.get("student_answer", "")
    
    # Mark the answer
    result = mark_with_feedback(student_answer, int(question_id))
    score = result.get("score", 0)
    is_correct = result.get("match_type", "") == "exact"
    
    # Record progress in DB
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("SELECT topic FROM questions WHERE id = %s", (question_id,))
        row = cur.fetchone()
        topic = row[0] if row else "unknown"
        
        cur.execute('''
            INSERT INTO student_progress (student_name, question_id, topic, score, is_correct)
            VALUES (%s, %s, %s, %s, %s)
        ''', (student_name, question_id, topic, score, is_correct))
        conn.commit()
        
        return jsonify({
            "score": score,
            "is_correct": is_correct,
            "topic": topic,
            "feedback": result.get("feedback", ""),
            "status": "ok"
        })
    finally:
        conn.close()

@app.route("/api/diagnose/<student_name>")
def diagnose_api(student_name):
    conn = get_db()
    try:
        result = detect_misconceptions(student_name, conn)
        return jsonify(result)
    finally:
        conn.close()


@app.route("/api/smart", methods=["POST"])
def smart_api():
    data = request.get_json()
    student_name = data.get("student_name") or data.get("student", "anonymous")
    question_id = data.get("question_id")
    student_answer = data.get("student_answer", "")
    
    # Validate: question_id required
    if question_id is None:
        return jsonify({"error": "question_id required", "hint": "Provide a numeric question_id from the database"}), 400
    
    # Validate: question_id must be convertible to int
    try:
        qid_int = int(question_id)
    except (ValueError, TypeError):
        return jsonify({"error": "question_id must be an integer", "received": str(question_id)}), 400
    
    conn = get_db()
    try:
        result = smart_pipeline(student_name, qid_int, student_answer, conn)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)[:200]}), 500
    finally:
        conn.close()


# ===== AI Paper Quality Scorer =====


@app.route("/api/quality/score")
def quality_score():
    paper_id = request.args.get("paper", "latest")
    from ai_quality_scorer import AIQualityScorer
    scorer = AIQualityScorer()
    result = scorer.score_paper(paper_id)
    return jsonify(result)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5100, debug=False)



