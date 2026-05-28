import psycopg2


def get_next_question(student_name, conn):
    cur = conn.cursor()
    # Find weakest topic (lowest avg score)
    cur.execute('''
        SELECT topic, AVG(score) as avg_score
        FROM student_progress
        WHERE student_name = %s
        GROUP BY topic
        ORDER BY avg_score ASC
        LIMIT 1
    ''', (student_name,))
    row = cur.fetchone()
    weak_topic = row[0] if row else None

    # Pick unanswered question from that topic
    if weak_topic:
        cur.execute('''
            SELECT q.id FROM questions q
            WHERE q.topic = %s
            AND q.id NOT IN (
                SELECT question_id FROM student_progress
                WHERE student_name = %s
            )
            ORDER BY RANDOM() LIMIT 1
        ''', (weak_topic, student_name))
    else:
        cur.execute('''
            SELECT q.id FROM questions q
            WHERE q.id NOT IN (
                SELECT question_id FROM student_progress
                WHERE student_name = %s
            )
            ORDER BY RANDOM() LIMIT 1
        ''', (student_name,))

    row = cur.fetchone()
    if row:
        return row[0], weak_topic

    # Fallback
    cur.execute("SELECT id FROM questions ORDER BY RANDOM() LIMIT 1")
    row = cur.fetchone()
    return row[0] if row else 1, weak_topic
