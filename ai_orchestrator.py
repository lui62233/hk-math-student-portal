"""AI Orchestrator: coordinates all 6 engines into a smart pipeline."""


def smart_pipeline(student_name, question_id, student_answer, conn):
    """Full AI pipeline: Mark → Diagnose → Recommend → Hint"""
    result = {"student": student_name, "pipeline": []}

    # Step 1: Mark the answer
    import sys
    sys.path.insert(0, r"D:\S1\_question_bank")
    from mark_engine import mark_with_feedback
    mark_result = mark_with_feedback(student_answer, int(question_id))
    result["mark"] = {
        "score": mark_result.get("score", 0),
        "status": mark_result.get("status", "UNKNOWN"),
    }
    result["pipeline"].append("marked")

    # Step 2: If wrong, diagnose misconceptions
    if mark_result.get("status") != "CORRECT":
        from misconception_engine import detect_misconceptions
        diag = detect_misconceptions(student_name, conn)
        result["diagnosis"] = {
            "weak_areas": diag.get("weak_areas", [])[:2],
            "total_errors": diag.get("total_errors", 0),
        }
        result["pipeline"].append("diagnosed")
    else:
        result["diagnosis"] = {"status": "correct", "message": "Great job!"}
        result["pipeline"].append("correct_skip_diagnosis")

    # Step 3: Recommend next question
    from adaptive_engine import get_next_question
    next_q = get_next_question(student_name, conn)
    result["next_question"] = {
        "question_id": next_q[0],
        "weak_topic": next_q[1],
    }
    result["pipeline"].append("recommended")

    # Step 4: If stuck, generate hint for next question
    from tutor_engine import get_hint
    hint_result, _ = get_hint(next_q[0], "", conn)
    result["hint"] = hint_result.get("hints", ["Try your best!"])[0]
    result["pipeline"].append("hint_ready")

    return result
