import psycopg2
import re


def get_hint(question_id, student_answer, conn):
    cur = conn.cursor()
    cur.execute('SELECT question_text, answer, topic, difficulty FROM questions WHERE id = %s', (question_id,))
    row = cur.fetchone()
    if not row:
        return {'error': 'Question not found'}, None

    question, correct_answer, topic, difficulty = row

    hints = generate_hints(question, correct_answer, topic, difficulty)

    is_correct = student_answer.strip().lower() == correct_answer.strip().lower() if student_answer and correct_answer else False

    return {
        'question_id': question_id,
        'topic': topic,
        'is_correct': is_correct,
        'hints': hints,
        'hint_level': 1
    }, is_correct


def generate_hints(question_text, answer, topic, difficulty):
    hints = []

    hints.append(f'This is a {topic} question. Think about what formulas or concepts relate to this topic.')

    numbers = re.findall(r'\d+', question_text)
    if numbers:
        hints.append(f'Key numbers in the question: {", ".join(numbers[:5])}. What operation connects them?')

    ops = {
        'Algebra': 'Try isolating the variable by performing inverse operations.',
        'Geometry': 'Draw a diagram and label all known values.',
        'Statistics': 'Organize your data and identify which measure to calculate.',
        'Arithmetic': 'Break the problem into smaller steps.',
        'Ratio': 'Set up a proportion with the given ratios.',
        'Percentage': 'Convert percentages to decimals and set up the equation.',
    }
    topic_hint = 'Identify what type of problem this is and the appropriate method.'
    for key, val in ops.items():
        if key.lower() in (topic or '').lower():
            topic_hint = val
            break
    hints.append(topic_hint)

    if answer and answer.strip():
        hints.append(f'The answer has {len(answer.strip())} characters. Try working through the steps systematically.')

    return hints


def get_next_hint(question_id, hint_level, conn):
    cur = conn.cursor()
    cur.execute('SELECT question_text, answer FROM questions WHERE id = %s', (question_id,))
    row = cur.fetchone()
    if not row:
        return {'error': 'Question not found'}

    question, answer = row

    progressive_hints = {
        2: f'Focus on: {question[:100]}... What is the FIRST step?',
        3: 'Try calculating with these steps: 1) Identify known values  2) Apply the formula  3) Solve step by step',
        4: f'The answer format resembles: {"*" * len(answer.strip()) if answer else "a number"}',
        5: f'Final hint: The answer begins with "{answer.strip()[:2] if answer else "?"}..."',
    }

    return {
        'question_id': question_id,
        'hint_level': min(hint_level + 1, 5),
        'hint': progressive_hints.get(hint_level + 1, 'No more hints available. Try your best answer!')
    }
