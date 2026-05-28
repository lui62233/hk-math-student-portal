#!/usr/bin/env python3
"""
Feedback Engine — Rules-driven, zero-AI learning feedback generator.
Integrates with mark_engine.py and PostgreSQL question_bank.
"""

import json
import sys
from dataclasses import dataclass, field
from typing import Any

import psycopg2
import psycopg2.extras

sys.stdout.reconfigure(encoding='utf-8')

from mark_engine import MarkResult

DB_CONFIG = "host=localhost dbname=question_bank user=postgres"
BANK_PATH = r'.\FINAL_MEGA_BANK.json'

# -- Topic-specific hint templates --
TOPIC_HINTS: dict[str, str] = {
    'fractions': 'Remember to find a common denominator before adding or subtracting fractions.',
    'algebra': 'Try isolating the variable by performing the same operation on both sides of the equation.',
    'geometry': 'Draw a diagram and label all known values. Check which formula applies to the given shape.',
    'trigonometry': 'Identify which trigonometric ratio (sin, cos, tan) relates the known and unknown sides.',
    'percentages': 'Convert the percentage to a decimal first, then set up the equation.',
    'ratios': 'Write the ratio as a fraction and look for equivalent forms.',
    'probability': 'Count the favourable outcomes and divide by the total number of possible outcomes.',
    'statistics': 'Check which measure (mean, median, mode) the question is asking for.',
    'number': 'Break the problem into smaller steps. Check your order of operations.',
    'measurement': 'Make sure all units are the same before calculating.',
    'equations': 'Substitute the given value into the equation and simplify step by step.',
    'graphs': 'Read the axes labels carefully. Identify what each point or line represents.',
    'area': 'Check you are using the correct formula for this shape.',
    'volume': 'Identify the 3D shape and recall its volume formula.',
    'angles': 'Remember: angles on a straight line sum to 180°, angles around a point sum to 360°.',
}

DEFAULT_HINT = 'Break the problem into smaller steps. Check each step carefully before moving on.'


@dataclass
class Feedback:
    status: str
    score: str
    message: str
    hint: str
    related_topics: list[str]
    suggested_practice: list[int]


class FeedbackEngine:
    def __init__(self, db_config: str = DB_CONFIG):
        self._conn = None
        self._db_config = db_config
        self._bank_cache: list | None = None

    @property
    def conn(self):
        if self._conn is None or self._conn.closed:
            self._conn = psycopg2.connect(self._db_config)
        return self._conn

    def _load_bank(self) -> list:
        if self._bank_cache is None:
            with open(BANK_PATH, 'r', encoding='utf-8') as f:
                self._bank_cache = json.load(f)['questions']
        return self._bank_cache

    def _get_question(self, question_id: int) -> dict:
        bank = self._load_bank()
        if 0 <= question_id < len(bank):
            return bank[question_id]
        return {}

    def _get_practice_ids(self, topic: str, form: str, exclude_id: int, limit: int = 5) -> list[int]:
        """Find similar questions from PostgreSQL: same topic, same form, different question."""
        cur = self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT id FROM questions
            WHERE topic = %s
              AND form = %s
              AND id != %s
              AND answer IS NOT NULL
              AND answer != ''
            ORDER BY RANDOM()
            LIMIT %s
        """, (topic, form, exclude_id, limit))
        rows = cur.fetchall()
        cur.close()
        return [r['id'] for r in rows]

    def _get_hint(self, topic: str) -> str:
        topic_lower = topic.lower().strip()
        for key, hint in TOPIC_HINTS.items():
            if key in topic_lower:
                return hint
        return DEFAULT_HINT

    def _get_related_topics(self, topic: str) -> list[str]:
        """Return related/sibling topics from the bank for further study."""
        bank = self._load_bank()
        related = set()
        topic_lower = topic.lower().strip()

        # Collect topics that co-appear with similar difficulty/domain
        for q in bank:
            qt = (q.get('topic') or '').lower().strip()
            if qt == topic_lower:
                continue
            if qt and self._topics_related(topic_lower, qt):
                related.add(qt)

        return sorted(related)[:5]

    @staticmethod
    def _topics_related(a: str, b: str) -> bool:
        """Check if two topics are in the same domain."""
        domains = [
            {'fractions', 'decimals', 'percentages', 'ratios', 'number'},
            {'algebra', 'equations', 'expressions', 'formulae', 'sequences'},
            {'geometry', 'angles', 'area', 'volume', 'shapes', 'measurement'},
            {'trigonometry', 'pythagoras', 'bearings'},
            {'statistics', 'probability', 'graphs', 'charts'},
        ]
        for domain in domains:
            a_in = any(d in a for d in domain)
            b_in = any(d in b for d in domain)
            if a_in and b_in:
                return True
        return False

    def generate(self, result: MarkResult, question_id: int, student_answer: str = '') -> Feedback:
        q = self._get_question(question_id)
        topic = (q.get('topic') or '').strip()
        form = (q.get('form') or '')
        if isinstance(form, (int, float)):
            form = str(int(form)) if form == int(form) else str(form)
        difficulty = q.get('difficulty', '') or q.get('difficulty_name', '') or ''

        score_str = f"{int(result.score)}/{result.max_score}"
        related = self._get_related_topics(topic)
        practice_ids = self._get_practice_ids(topic, form, question_id)

        if result.status == 'CORRECT':
            return self._feedback_correct(result, score_str, topic, difficulty, related, practice_ids)
        elif result.status == 'PARTIAL':
            return self._feedback_partial(result, score_str, topic, related, practice_ids)
        elif result.status == 'INCORRECT':
            hint = self._get_hint(topic)
            return self._feedback_incorrect(result, score_str, topic, hint, related, practice_ids)
        else:  # REVIEW
            return self._feedback_review(score_str)

    def _feedback_correct(self, result: MarkResult, score_str: str, topic: str,
                          difficulty: str, related: list[str], practice: list[int]) -> Feedback:
        messages = [
            f"Excellent! You scored {score_str} on {topic}. Well done!",
            f"Great work! Full marks ({score_str}) on {topic}. You've mastered this topic.",
            f"Perfect! {score_str} on {topic}. You clearly understand this material.",
        ]
        idx = hash(str(result.score)) % len(messages)

        harder_note = ""
        if difficulty:
            harder_note = f" Try a harder difficulty level to challenge yourself further."

        return Feedback(
            status='CORRECT',
            score=score_str,
            message=messages[idx] + harder_note,
            hint=f"You've mastered {topic}. Consider exploring: {', '.join(related[:3]) if related else 'more advanced topics'}.",
            related_topics=related,
            suggested_practice=practice,
        )

    def _feedback_partial(self, result: MarkResult, score_str: str, topic: str,
                          related: list[str], practice: list[int]) -> Feedback:
        parts_detail = result.details.get('parts', {})
        correct_parts = [p for p, v in parts_detail.items() if v in ('exact', 'numeric')]
        wrong_parts = [p for p, v in parts_detail.items() if v == 'mismatch']

        msg = f"Good effort! You scored {score_str} on {topic}."
        if correct_parts:
            msg += f" Part(s) {', '.join(correct_parts)} are correct."
        if wrong_parts:
            msg += f" Part(s) {', '.join(wrong_parts)} need review."

        focus = f"Review: {', '.join(wrong_parts)}" if wrong_parts else f"Review the full solution for {topic}."

        return Feedback(
            status='PARTIAL',
            score=score_str,
            message=msg,
            hint=f"{focus} Practice similar questions to strengthen your understanding.",
            related_topics=related,
            suggested_practice=practice,
        )

    def _feedback_incorrect(self, result: MarkResult, score_str: str, topic: str,
                            hint: str, related: list[str], practice: list[int]) -> Feedback:
        return Feedback(
            status='INCORRECT',
            score=score_str,
            message=f"Keep trying! You scored {score_str} on {topic}. Don't worry — mistakes are part of learning.",
            hint=hint,
            related_topics=related,
            suggested_practice=practice,
        )

    def _feedback_review(self, score_str: str) -> Feedback:
        return Feedback(
            status='REVIEW',
            score=score_str,
            message="This answer needs to be reviewed by your teacher. They will provide detailed feedback soon.",
            hint="In the meantime, review your notes on this topic and check your working steps.",
            related_topics=[],
            suggested_practice=[],
        )

    def close(self):
        if self._conn and not self._conn.closed:
            self._conn.close()

    def __del__(self):
        self.close()


# -- Run self-test --
def run_self_test(num_questions: int = 20) -> dict:
    import random
    random.seed(42)

    from mark_engine import mark_answer, _get_answered_questions

    engine = FeedbackEngine()
    answered = _get_answered_questions()

    if len(answered) > num_questions:
        test_set = random.sample(answered, num_questions)
    else:
        test_set = answered[:num_questions]

    results = {
        'total': len(test_set),
        'correct': 0,
        'partial': 0,
        'incorrect': 0,
        'review': 0,
        'with_practice': 0,
        'with_related': 0,
        'details': [],
    }

    wrong_answers = ["0", "1", "-999", "abc", "x=100"]

    for idx, q in test_set:
        model_answer = q['answer']
        topic = q.get('topic', 'Unknown')

        # Correct answer test
        mr = mark_answer(model_answer, idx)
        fb = engine.generate(mr, idx, model_answer)

        entry = {
            'idx': idx,
            'topic': topic,
            'correct_fb': {
                'status': fb.status,
                'score': fb.score,
                'message': fb.message[:80],
                'hint': fb.hint[:80],
                'related_topics': fb.related_topics,
                'practice_count': len(fb.suggested_practice),
            }
        }

        if fb.status == 'CORRECT':
            results['correct'] += 1
        elif fb.status == 'PARTIAL':
            results['partial'] += 1
        elif fb.status == 'INCORRECT':
            results['incorrect'] += 1
        else:
            results['review'] += 1

        if fb.suggested_practice:
            results['with_practice'] += 1
        if fb.related_topics:
            results['with_related'] += 1

        # Wrong answer test
        wa = wrong_answers[idx % len(wrong_answers)]
        wr = mark_answer(wa, idx)
        wfb = engine.generate(wr, idx, wa)
        entry['wrong_fb'] = {
            'input': wa[:30],
            'status': wfb.status,
            'score': wfb.score,
            'message': wfb.message[:80],
            'hint': wfb.hint[:80],
        }

        results['details'].append(entry)

    engine.close()
    return results


def print_report(results: dict) -> None:
    print("=" * 70)
    print("  FEEDBACK ENGINE — SELF-TEST REPORT")
    print("=" * 70)
    print(f"  Questions tested: {results['total']}")
    print(f"  CORRECT feedbacks:   {results['correct']}")
    print(f"  PARTIAL feedbacks:   {results['partial']}")
    print(f"  INCORRECT feedbacks: {results['incorrect']}")
    print(f"  REVIEW feedbacks:    {results['review']}")
    print(f"  With practice links: {results['with_practice']}/{results['total']}")
    print(f"  With related topics: {results['with_related']}/{results['total']}")
    print()

    status = 'PASS' if results['correct'] + results['partial'] > 0 else 'FAIL'
    print(f"  STATUS: {status}")
    print()

    print("-" * 70)
    print("  SAMPLE FEEDBACKS:")
    print("-" * 70)
    for d in results['details'][:5]:
        cf = d['correct_fb']
        wf = d['wrong_fb']
        print(f"  Q{d['idx']} [{d['topic'][:40]}]")
        print(f"    Correct  → {cf['status']} | {cf['score']} | {cf['message']}")
        print(f"    Wrong    → {wf['status']} | {wf['score']} | {wf['message']}")
        print(f"    Practice → {cf['practice_count']} questions | Related → {cf['related_topics'][:3]}")
        print()

    print("=" * 70)


if __name__ == '__main__':
    results = run_self_test(20)
    print_report(results)
