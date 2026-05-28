# Misconception patterns per topic
MISCONCEPTIONS = {
    "Algebra": {
        "sign_error": "Check your positive/negative signs when moving terms",
        "distributive": "Remember to multiply EVERY term inside brackets",
        "inverse_ops": "Use inverse operations in the correct order",
    },
    "Fractions": {
        "common_denom": "Find a common denominator before adding/subtracting",
        "reciprocal": "When dividing, multiply by the reciprocal",
        "simplify": "Always simplify your final answer",
    },
    "Geometry": {
        "angle_sum": "Angles in a triangle sum to 180 degrees",
        "parallel_lines": "Check alternate/corresponding angle rules",
        "units": "Make sure all measurements use the same units",
    },
    "Statistics": {
        "mean_calc": "Sum all values then divide by count",
        "median_sort": "Sort data first, then find the middle value",
        "mode_count": "Mode is the most frequent value, not the largest",
    },
    "Ratio": {
        "order": "Keep the ratio order consistent (first:second)",
        "total_parts": "Find total parts before calculating individual values",
        "units": "Convert to same units before comparing ratios",
    },
}


def detect_misconceptions(student_name, conn):
    """Analyze student's wrong answers to detect patterns"""
    cur = conn.cursor()
    cur.execute(
        """
        SELECT q.topic, q.question_text, q.answer as correct_answer, sp.score
        FROM student_progress sp
        JOIN questions q ON sp.question_id = q.id
        WHERE sp.student_name = %s AND sp.status != 'CORRECT'
        ORDER BY sp.created_at DESC
        LIMIT 20
    """,
        (student_name,),
    )

    errors = cur.fetchall()
    if not errors:
        return {
            "student": student_name,
            "weak_areas": [],
            "message": "No errors found — great job!",
        }

    # Count errors by topic
    topic_errors = {}
    for topic, question, correct_ans, score in errors:
        if topic not in topic_errors:
            topic_errors[topic] = []
        topic_errors[topic].append(
            {
                "question": question[:80],
                "correct_answer": correct_ans,
                "score": score,
            }
        )

    # Match misconceptions
    weak_areas = []
    for topic, errs in sorted(topic_errors.items(), key=lambda x: -len(x[1])):
        misconceptions = MISCONCEPTIONS.get(topic, {})
        area = {
            "topic": topic,
            "error_count": len(errs),
            "possible_issues": (
                list(misconceptions.values())[:3]
                if misconceptions
                else ["Review this topic"]
            ),
            "recent_errors": errs[:3],
        }
        weak_areas.append(area)

    return {
        "student": student_name,
        "total_errors": len(errors),
        "weak_areas": weak_areas,
        "recommendation": (
            f"Focus on: {weak_areas[0]['topic']}" if weak_areas else "Keep practicing!"
        ),
    }
