#!/usr/bin/env python3
r"""
Math Marking Engine -- Deterministic, zero-AI, 4-level matching strategy.
Reads from .\FINAL_MEGA_BANK.json
"""

import json
import re
import sys
from fractions import Fraction
from dataclasses import dataclass, field
from typing import Any

sys.stdout.reconfigure(encoding='utf-8')

# -- Unicode math symbol map --
UNICODE_MATH_MAP = {
    '': '*', '': '-', '': '=', '': '/',
    '': '^', '': '.', '': '+/-', '': '<=',
    '': '>=', '': 'deg', '': '*', '': '->',
    '': '{', '': '}', '': '[', '': ']',
    '': '(', '': ')', '': '(', '': ')',
    '´': "'", '‘': "'", '’': "'", '“': '"',
    '”': '"', '–': '-', '—': '-', '―': '-',
    '−': '-', '×': '*', '÷': '/', '≤': '<=',
    '≥': '>=', '°': 'deg', 'π': 'pi', '√': 'sqrt',
    '±': '+/-', '½': '1/2', '¼': '1/4', '¾': '3/4',
    '⅓': '1/3', '⅔': '2/3', '²': '^2', '³': '^3',
    '̃': '', '̣': '',
}

REMOVE_CHARS = str.maketrans('', '', '​‌‍‎‏⁠﻿\xa0\r')

BANK_PATH = r'.\FINAL_MEGA_BANK.json'

_questions_list: list | None = None
_questions_answered: list | None = None



# === PG Fallback ===
def _get_answer_from_pg(question_id: int):
    """Fallback: fetch answer from PostgreSQL when JSON bank misses it."""
    try:
        import psycopg2
        conn = psycopg2.connect(
            host="localhost", dbname="question_bank",
            user="postgres", password=""
        )
        cur = conn.cursor()
        cur.execute("SELECT answer FROM questions WHERE id = %s", (question_id,))
        row = cur.fetchone()
        conn.close()
        if row and row[0]:
            return {"id": question_id, "answer": row[0], "has_answer": True}
    except Exception:
        pass
    return None

def _load_bank() -> list:
    """Load question bank, return list of all questions."""
    global _questions_list
    if _questions_list is None:
        with open(BANK_PATH, 'r', encoding='utf-8') as f:
            raw = json.load(f)
        _questions_list = raw['questions']
    return _questions_list


def _get_answered_questions() -> list:
    """Return list of (index, question) tuples for questions with non-null answers and marks > 0."""
    global _questions_answered
    if _questions_answered is None:
        bank = _load_bank()
        _questions_answered = []
        for i, q in enumerate(bank):
            ans = q.get('answer')
            if ans and ans.strip():
                marks = q.get('marks', 0) or q.get('total_marks', 0)
                if marks > 0:
                    _questions_answered.append((i, q))
    return _questions_answered


# -- Normalization --

def normalize(text: str) -> str:
    if not text:
        return ''
    text = text.translate(REMOVE_CHARS)
    for u, a in UNICODE_MATH_MAP.items():
        text = text.replace(u, a)
    text = ' '.join(text.split())
    text = re.sub(r'\b1A\b', '', text)
    text = re.sub(r'\bM\d*\b', '', text)
    text = re.sub(r'https?://\S+', '', text)
    text = re.sub(r'TB\([^)]*\).*$', '', text)
    text = re.sub(r'Page \d+ of \d+', '', text)
    text = ' '.join(text.split()).strip()
    return text


def strip_working(text: str) -> str:
    if not text:
        return ''
    text = normalize(text)
    lines = text.split('\n')
    candidates = []
    for line in lines:
        line = line.strip()
        if not line or '~ End ~' in line or line.startswith('http'):
            continue
        line = re.sub(r'^[\*\-–•→\>\-]+\s*', '', line)
        candidates.append(line)
    return '\n'.join(candidates)


# -- Number extraction --

def extract_numbers(text: str) -> list[Fraction]:
    if not text:
        return []
    text = normalize(text)
    numbers = []
    seen_spans = set()

    # Mixed fraction: "1 1/2"
    for m in re.finditer(r'(-?\d+)\s+(\d+)\s*/\s*(\d+)', text):
        whole = int(m.group(1))
        num = int(m.group(2))
        den = int(m.group(3))
        if den != 0:
            if whole >= 0:
                val = Fraction(whole * den + num, den)
            else:
                val = Fraction(whole * den - num, den)
            numbers.append(val)
            seen_spans.add((m.start(), m.end()))

    # Simple fraction: "-5/16"
    for m in re.finditer(r'(?<![)\d])(-?\d+)\s*/\s*(-?\d+)(?![(\d])', text):
        if (m.start(), m.end()) in seen_spans:
            continue
        num = int(m.group(1))
        den = int(m.group(2))
        if den != 0:
            numbers.append(Fraction(num, den))
            seen_spans.add((m.start(), m.end()))

    # Decimal: 3.14, 0.5, .5
    for m in re.finditer(r'(?<!\d)(-?\.?\d+\.\d+)(?!\d)', text):
        if (m.start(), m.end()) in seen_spans:
            continue
        try:
            numbers.append(Fraction(m.group(1)))
            seen_spans.add((m.start(), m.end()))
        except (ValueError, ZeroDivisionError):
            pass

    # Integers (not part of fraction/decimal)
    for m in re.finditer(r'(?<![\d\./])(-?\d+)(?![\d\./])', text):
        if (m.start(), m.end()) in seen_spans:
            continue
        numbers.append(Fraction(int(m.group(1))))
        seen_spans.add((m.start(), m.end()))

    return numbers


def extract_final_number(text: str) -> Fraction | None:
    """Extract the most likely final answer number."""
    text = normalize(text)

    # = X at end of line
    matches = re.findall(r'=\s*(-?\d+(?:\.\d+)?(?:\s*/\s*\d+)?)\s*(?:\([^)]*\))?\s*$', text, re.MULTILINE)
    if matches:
        return _parse_number(matches[-1])

    # Any = X
    matches = re.findall(r'=\s*(-?\d+(?:\.\d+)?(?:\s*/\s*\d+)?)', text)
    if matches:
        return _parse_number(matches[-1])

    # Standalone number at end
    m = re.search(r'(?:^|\s)(-?\d+(?:\.\d+)?(?:\s*/\s*\d+)?)\s*$', text)
    if m:
        return _parse_number(m.group(1))

    return None


def _parse_number(s: str) -> Fraction | None:
    s = s.strip()
    try:
        if '/' in s:
            parts = re.split(r'\s*/\s*', s)
            if len(parts) == 2:
                return Fraction(int(parts[0]), int(parts[1]))
        return Fraction(s)
    except (ValueError, ZeroDivisionError):
        return None


def extract_all_final_numbers(text: str) -> list[Fraction]:
    text = normalize(text)
    results = []
    for m in re.finditer(r'=\s*(-?\d+(?:\.\d+)?(?:\s*/\s*\d+)?)', text):
        val = _parse_number(m.group(1))
        if val is not None:
            results.append(val)
    return results


# -- Part splitting --

def split_parts(text: str) -> dict[str, str]:
    if not text:
        return {}
    text = normalize(text)
    # Match (a), (b), (c), (d) or (i), (ii)
    part_pattern = re.compile(r'\(([a-dA-D]|[ivx]+)\)\s*')
    splits = part_pattern.split(text)
    parts = {}
    current_part = '_pre'
    for i, chunk in enumerate(splits):
        if i == 0:
            if chunk.strip():
                parts[current_part] = chunk.strip()
            continue
        if i % 2 == 1:
            current_part = chunk.lower()
        else:
            # Only take up to the next part marker or end
            parts[current_part] = chunk.strip()
    return parts


# -- Matching levels --

def match_exact(student: str, model: str) -> tuple[bool, float]:
    s = normalize(student)
    m = normalize(model)
    if s == m:
        return True, 1.0
    s_clean = re.sub(r'[^\w\s\-\+\*\/\=\(\)\[\]\{\}\.\,\<\>\@\^]', '', s).strip()
    m_clean = re.sub(r'[^\w\s\-\+\*\/\=\(\)\[\]\{\}\.\,\<\>\@\^]', '', m).strip()
    if s_clean and m_clean and s_clean == m_clean:
        return True, 1.0
    return False, 0.0


def match_numeric(student: str, model: str) -> tuple[bool, float]:
    s_final = extract_final_number(student)
    m_final = extract_final_number(model)

    if s_final is not None and m_final is not None:
        if s_final == m_final:
            return True, 0.95
        if abs(float(s_final) - float(m_final)) < 1e-9:
            return True, 0.95

    # If final numbers don't match, compare full number sets
    s_nums = extract_numbers(student)
    m_nums = extract_numbers(model)

    if not s_nums or not m_nums:
        return False, 0.0

    s_set = set(s_nums)
    m_set = set(m_nums)

    # Exact set match: all numbers identical
    if s_set == m_set:
        return True, 0.90

    # Subset: only allow if student provides >1 number and matches most model numbers
    # A single number matching a complex model is likely coincidence
    if len(s_nums) >= 3 and len(s_set & m_set) >= len(m_set) * 0.8:
        return True, 0.80
    if len(s_nums) >= 3 and m_set.issubset(s_set):
        return True, 0.80
    if len(s_nums) >= 2 and s_set.issubset(m_set) and len(s_set) >= len(m_set) * 0.6:
        return True, 0.75

    return False, 0.0


def match_structural(student: str, model: str) -> tuple[bool, float, dict]:
    s_parts = split_parts(student)
    m_parts = split_parts(model)

    if not s_parts or not m_parts:
        return False, 0.0, {}

    common = set(s_parts.keys()) & set(m_parts.keys())
    common.discard('_pre')

    if not common:
        return False, 0.0, {}

    matched = 0
    total = len(common)
    details = {}

    for part in sorted(common):
        s_part = s_parts[part]
        m_part = m_parts[part]
        ok, _ = match_exact(s_part, m_part)
        if ok:
            matched += 1
            details[part] = 'exact'
            continue
        ok, _ = match_numeric(s_part, m_part)
        if ok:
            matched += 1
            details[part] = 'numeric'
            continue
        details[part] = 'mismatch'

    score = matched / max(total, 1)
    return score > 0, score, details


# -- Main marking function --

@dataclass
class MarkResult:
    score: float
    max_score: int
    confidence: float
    details: dict[str, Any]
    status: str  # CORRECT, PARTIAL, INCORRECT, REVIEW


def mark_answer(student_answer: str, question_id: int) -> MarkResult:
    """
    Mark a student answer against the model answer for a given question.

    Args:
        student_answer: The student's submitted answer text
        question_id: 0-based index into the questions array

    Returns:
        MarkResult with score, max_score, confidence, details, status
    """
    bank = _load_bank()
    qid = int(question_id)

    if qid < 0 or qid >= len(bank):
        return MarkResult(
            score=0, max_score=0, confidence=0.0,
            details={'error': f'Question index {qid} out of range (0-{len(bank)-1})'},
            status='REVIEW'
        )

    q = bank[qid]
    model_answer = q.get('answer') or ''
    max_marks = q.get('marks', 0) or q.get('total_marks', 0) or 1
    marking_scheme = q.get('marking_scheme', [])

    if not model_answer.strip():
        return MarkResult(
            score=0, max_score=max_marks, confidence=0.0,
            details={'error': 'No model answer available'},
            status='REVIEW'
        )

    # -- Level 1: Exact match --
    ok, conf = match_exact(student_answer, model_answer)
    if ok:
        return MarkResult(
            score=max_marks, max_score=max_marks, confidence=conf,
            details={'level': 1, 'method': 'exact_match'},
            status='CORRECT'
        )

    s_stripped = strip_working(student_answer)
    m_stripped = strip_working(model_answer)
    ok, conf = match_exact(s_stripped, m_stripped)
    if ok:
        return MarkResult(
            score=max_marks, max_score=max_marks, confidence=conf,
            details={'level': 1, 'method': 'exact_match_stripped'},
            status='CORRECT'
        )

    # -- Level 2: Numeric match --
    ok, conf = match_numeric(student_answer, model_answer)
    if ok:
        return MarkResult(
            score=max_marks, max_score=max_marks, confidence=conf,
            details={'level': 2, 'method': 'numeric_match'},
            status='CORRECT'
        )

    # -- Level 3: Structural match (multi-part) --
    ok, score_fraction, part_details = match_structural(student_answer, model_answer)
    if ok and score_fraction >= 0.5:
        earned = round(max_marks * score_fraction)
        status = 'CORRECT' if score_fraction >= 0.99 else 'PARTIAL'
        return MarkResult(
            score=earned, max_score=max_marks, confidence=0.80 * score_fraction,
            details={'level': 3, 'method': 'structural_match', 'parts': part_details, 'fraction': score_fraction},
            status=status
        )

    # -- Level 3b: Final number match --
    s_final = extract_final_number(student_answer)
    m_final = extract_final_number(model_answer)
    if s_final is not None and m_final is not None and s_final == m_final:
        return MarkResult(
            score=max_marks, max_score=max_marks, confidence=0.85,
            details={'level': 3, 'method': 'final_number_match'},
            status='CORRECT'
        )

    # -- Level 3c: Contains final answer (word-boundary check) --
    m_text = normalize(model_answer)
    s_text = normalize(student_answer)
    if m_final is not None:
        m_final_str = str(m_final)
        m_final_decimal = f'{float(m_final):g}'
        # Use word-boundary matching to avoid "1" matching inside "100"
        escaped = re.escape(m_final_str)
        escaped_dec = re.escape(m_final_decimal)
        if re.search(r'(?<!\d)' + escaped + r'(?!\d)', s_text) or \
           (m_final_decimal != m_final_str and re.search(r'(?<!\d)' + escaped_dec + r'(?!\d)', s_text)):
            return MarkResult(
                score=max_marks, max_score=max_marks, confidence=0.80,
                details={'level': 3, 'method': 'contains_final_answer'},
                status='CORRECT'
            )

    # -- Level 3d: Number set overlap (partial credit) --
    s_nums = extract_numbers(s_text)
    m_nums = extract_numbers(m_text)
    if s_nums and m_nums:
        m_set = set()
        for n in m_nums:
            m_set.add(str(n))
            m_set.add(f'{float(n):g}')
        s_str_set = set()
        for n in s_nums:
            s_str_set.add(str(n))
            s_str_set.add(f'{float(n):g}')
        overlap = m_set & s_str_set
        if len(overlap) >= len(m_set) * 0.5:
            frac = len(overlap) / max(len(m_set), 1)
            score = round(max_marks * frac)
            return MarkResult(
                score=score, max_score=max_marks, confidence=0.70,
                details={'level': 3, 'method': 'number_set_overlap', 'overlap': len(overlap), 'total': len(m_set)},
                status='PARTIAL'
            )

    # -- Level 4: REVIEW --
    return MarkResult(
        score=0, max_score=max_marks, confidence=0.0,
        details={'level': 4, 'method': 'review_required', 'note': 'Cannot confidently match'},
        status='REVIEW'
    )


def mark_with_feedback(student_answer: str, question_id: int) -> dict:
    """Mark an answer and generate learning feedback in one call.

    Returns a dict with both MarkResult fields and Feedback fields.
    """
    result = mark_answer(student_answer, question_id)
    from feedback_engine import FeedbackEngine
    engine = FeedbackEngine()
    try:
        fb = engine.generate(result, question_id, student_answer)
    finally:
        engine.close()
    return {
        'score': result.score,
        'max_score': result.max_score,
        'confidence': result.confidence,
        'details': result.details,
        'status': fb.status,
        'score_display': fb.score,
        'message': fb.message,
        'hint': fb.hint,
        'related_topics': fb.related_topics,
        'suggested_practice': fb.suggested_practice,
    }


# -- Self-test --

def run_self_test(num_questions: int = 50) -> dict:
    answered = _get_answered_questions()

    import random
    random.seed(42)
    if len(answered) > num_questions:
        test_set = random.sample(answered, num_questions)
    else:
        test_set = answered[:num_questions]

    results = {
        'total': len(test_set),
        'correct_full_marks': 0,
        'correct_partial': 0,
        'correct_failed': 0,
        'wrong_detected': 0,
        'wrong_missed': 0,
        'review_count': 0,
        'details': []
    }

    wrong_answers = ["0", "1", "-999", "abc", "x=100", "3.14159", "1/7", "-1000", "", "not an answer"]

    for idx, q in test_set:
        model_answer = q['answer']
        max_marks = q.get('marks', 0) or q.get('total_marks', 0)
        topic = q.get('topic', 'Unknown')
        q_num = q.get('number', str(idx))

        r_correct = mark_answer(model_answer, idx)
        stripped = strip_working(model_answer)
        r_stripped = mark_answer(stripped, idx) if stripped != normalize(model_answer) else None

        wrong_results = []
        for wa in wrong_answers[:5]:
            wr = mark_answer(wa, idx)
            wrong_results.append(wr)

        detail = {
            'idx': idx,
            'q_num': q_num,
            'topic': topic,
            'max_marks': max_marks,
            'correct_test': {
                'score': r_correct.score,
                'max': r_correct.max_score,
                'status': r_correct.status,
                'confidence': r_correct.confidence,
                'details': r_correct.details
            }
        }

        if r_stripped:
            detail['stripped_test'] = {
                'score': r_stripped.score,
                'max': r_stripped.max_score,
                'status': r_stripped.status,
                'confidence': r_stripped.confidence,
            }

        detail['wrong_tests'] = [
            {'input': wa, 'score': wr.score, 'status': wr.status}
            for wa, wr in zip(wrong_answers[:5], wrong_results)
        ]

        if r_correct.status == 'CORRECT' and r_correct.score >= max_marks:
            results['correct_full_marks'] += 1
        elif r_correct.status == 'PARTIAL':
            results['correct_partial'] += 1
        else:
            results['correct_failed'] += 1
            if r_correct.status == 'REVIEW':
                results['review_count'] += 1

        all_wrong_detected = all(
            wr.status in ('REVIEW', 'PARTIAL') and wr.score < max_marks
            for wr in wrong_results
        )
        if all_wrong_detected:
            results['wrong_detected'] += 1
        else:
            results['wrong_missed'] += 1

        results['details'].append(detail)

    total = results['total']
    results['pass_rate'] = results['correct_full_marks'] / total * 100 if total else 0
    results['partial_rate'] = results['correct_partial'] / total * 100 if total else 0
    results['fail_rate'] = results['correct_failed'] / total * 100 if total else 0
    results['review_rate'] = results['review_count'] / total * 100 if total else 0
    results['wrong_detection_rate'] = results['wrong_detected'] / total * 100 if total else 0

    return results


def print_report(results: dict) -> None:
    print("=" * 70)
    print("  MATH MARKING ENGINE -- SELF-TEST REPORT")
    print("=" * 70)
    print(f"  Questions tested: {results['total']}")
    print(f"  Pass rate (correct -> full marks): {results['pass_rate']:.1f}%")
    print(f"  Partial rate (correct -> partial):  {results['partial_rate']:.1f}%")
    print(f"  Fail rate (correct -> wrong/review): {results['fail_rate']:.1f}%")
    print(f"  REVIEW rate:                        {results['review_rate']:.1f}%")
    print(f"  Wrong detection rate:               {results['wrong_detection_rate']:.1f}%")
    print()

    if results['review_rate'] > 20:
        print("  FAIL: REVIEW rate > 20% -- engine needs improvement")
    elif results['pass_rate'] < 100:
        print(f"  FAIL: Pass rate {results['pass_rate']:.1f}% < 100% required")
    else:
        print("  PASS: 100% pass rate achieved")

    print()
    print("-" * 70)
    print("  FAILURES / REVIEWS (correct answers not getting full marks):")
    print("-" * 70)
    for d in results['details']:
        ct = d['correct_test']
        if ct['status'] != 'CORRECT' or ct['score'] < d['max_marks']:
            print(f"  idx={d['idx']} Q{d['q_num']} [{d['topic'][:50]}] marks={d['max_marks']}")
            print(f"    Status: {ct['status']} Score: {ct['score']}/{ct['max_marks']}")
            print(f"    Details: {ct['details']}")
            print()

    print("-" * 70)
    print("  WRONG ANSWERS NOT DETECTED (false positives):")
    print("-" * 70)
    fp_count = 0
    for d in results['details']:
        for wt in d['wrong_tests']:
            if wt['status'] == 'CORRECT':
                print(f"  idx={d['idx']}: input='{wt['input']}' -> {wt['status']} score={wt['score']}")
                fp_count += 1
    if fp_count == 0:
        print("  (none)")
    print("=" * 70)


if __name__ == '__main__':
    results = run_self_test(50)
    print_report(results)

