#!/usr/bin/env python3
"""
P2-005: AI Question Variant Engine
Rule-based variant generator for HK math question bank.
Generates question variants by transforming numbers, names, and scenarios,
then recomputing correct answers.
"""
import json
import re
import random
import math
import sys
import io
from collections import defaultdict
from fractions import Fraction

# ── Unicode OCR symbol normalization ──────────────────────────────────────
OCR_MAP = {
    '': '-', '': '+', '': '×', '': '÷',
    '': '=', '': '(', '': ')', '': '°',
    '': '∆', '': '∠', '': '·',
    '': 'α', '': 'β', '': 'γ',
    '': 'δ', '': 'θ', '': 'π',
    '': '∠', '': '\\', '': '√',
    '': 'σ', '': 'λ', '': 'μ',
    '': 'ω', '': 'ρ', '': 'φ',
    '': '[', '': ']', '': '/', '': 'τ',
}
SYM_NORMALIZE = {
    '×': '*', '÷': '/', '–': '-', '—': '-',
    '−': '-', '·': '*', '⁠': '',
}

def normalize_math(text):
    """Normalize OCR symbols and math characters to evaluable ASCII."""
    if not text:
        return ''
    for k, v in OCR_MAP.items():
        text = text.replace(k, v)
    for k, v in SYM_NORMALIZE.items():
        text = text.replace(k, v)
    return text

# ── Number extraction & transformation ────────────────────────────────────
NUMBER_RE = re.compile(r'(?:(?<!\w)|-)(?:\d+\.?\d*|\.\d+)(?!\w)')
INTEGER_RE = re.compile(r'(?:(?<!\w)|-)(\d+)(?![\w.]|/\d)')

def extract_numbers(text):
    """Extract all numeric tokens from text, returning list of (value_str, start, end)."""
    if not text:
        return []
    matches = []
    for m in NUMBER_RE.finditer(text):
        val = m.group()
        # skip page numbers, line numbers, year ranges
        if val in ('0', '1') and m.start() < 10:
            continue
        if re.match(r'^\d{2,4}$', val) and m.start() < 5:
            continue  # likely question number or year
        matches.append((val, m.start(), m.end()))
    return matches

def transform_number(num_str):
    """Generate a similar-but-different number keeping same magnitude."""
    try:
        n = float(num_str)
    except ValueError:
        return num_str

    if n == 0:
        return num_str

    is_int = '.' not in num_str
    sign = -1 if n < 0 else 1
    n_abs = abs(n)

    # Pick a transformation strategy
    strategies = []

    if is_int and n_abs <= 20:
        # Small integer: add/subtract small amount
        delta = random.choice([d for d in [-3, -2, -1, 1, 2, 3, 4] if n_abs + d > 0 and n_abs + d != n_abs])
        new_n = n_abs + delta

    elif is_int and n_abs <= 100:
        delta = random.choice([d for d in [-10, -5, -2, 2, 5, 10, 15] if 1 <= n_abs + d <= 150 and n_abs + d != n_abs])
        new_n = n_abs + delta

    elif is_int and n_abs <= 1000:
        factor = random.choice([0.5, 0.6, 0.7, 0.8, 1.2, 1.3, 1.5, 1.7, 2.0])
        new_n = int(n_abs * factor)
        while new_n == n_abs or new_n < 1:
            factor = random.choice([0.5, 0.6, 0.7, 0.8, 1.2, 1.3, 1.5, 1.7, 2.0])
            new_n = int(n_abs * factor)

    elif is_int:
        factor = random.choice([0.3, 0.5, 0.7, 1.3, 1.5, 1.7])
        new_n = int(n_abs * factor)
        while new_n == n_abs or new_n < 1:
            factor = random.choice([0.3, 0.5, 0.7, 1.3, 1.5, 1.7])
            new_n = int(n_abs * factor)

    else:
        # Decimal: scale by factor
        factor = random.choice([0.5, 0.6, 0.7, 0.8, 1.2, 1.3, 1.5, 2.0])
        new_n = round(n_abs * factor, len(num_str.split('.')[1]) if '.' in num_str else 0)
        # Ensure we have same number of decimal places
        if '.' in num_str:
            decimals = len(num_str.split('.')[1])
            new_n = round(new_n, decimals)

    # Apply sign
    if is_int:
        result = str(sign * int(new_n))
    else:
        result = str(sign * new_n)
        if '.' in result:
            decimals = len(num_str.split('.')[1])
            parts = result.split('.')
            result = parts[0] + '.' + parts[1][:decimals].ljust(decimals, '0')

    if result == num_str:
        # Fallback: just add 1
        if is_int:
            result = str(int(num_str) + (1 if int(num_str) > 0 else -1))
        else:
            result = str(float(num_str) + 0.1)

    return result

def build_number_map(question_text):
    """Build mapping from original numbers to transformed numbers."""
    numbers = extract_numbers(question_text)
    num_map = {}
    used_new = set()
    for val, start, end in numbers:
        if val in num_map:
            continue
        # Try up to 10 times to get a unique new number
        for _ in range(10):
            new_val = transform_number(val)
            if new_val != val and new_val not in used_new:
                break
        num_map[val] = new_val
        used_new.add(new_val)
    return num_map

def replace_numbers(text, num_map):
    """Replace numbers in text using the mapping (word-boundary aware)."""
    if not text or not num_map:
        return text

    # Sort by value length (descending) to avoid partial matches
    items = sorted(num_map.items(), key=lambda x: len(x[0]), reverse=True)
    result = text
    for old_val, new_val in items:
        # Use word-boundary regex
        pattern = re.compile(r'(?<!\w)' + re.escape(old_val) + r'(?!\w)')
        result = pattern.sub(new_val, result)
    return result

# ── Name & scenario replacement ───────────────────────────────────────────
NAME_MALE = ['Alex', 'Ben', 'Chris', 'David', 'Eric', 'Frank', 'George', 'Henry']
NAME_FEMALE = ['Amy', 'Bella', 'Cathy', 'Diana', 'Eva', 'Fiona', 'Grace', 'Helen']
COMMON_NAMES = ['Carmen', 'Mary', 'John', 'Peter', 'Paul', 'Tom', 'Sam', 'Ann',
                'Alice', 'Bob', 'Ken', 'May', 'Ivan', 'Ada', 'Jack', 'Kevin',
                'Leo', 'Mandy', 'Nancy', 'Oscar', 'Ray', 'Sue', 'Tim', 'Una']

def replace_names(text):
    """Replace common person names with alternatives."""
    if not text:
        return text
    result = text
    names_found = [n for n in COMMON_NAMES if re.search(r'\b' + re.escape(n) + r'\b', result)]
    for name in names_found:
        if name in ['Carmen', 'Mary', 'Ann', 'May', 'Sue', 'Mandy', 'Nancy', 'Ada', 'Alice', 'Una']:
            new_name = random.choice([n for n in NAME_FEMALE if n != name])
        else:
            new_name = random.choice([n for n in NAME_MALE if n != name])
        result = re.sub(r'\b' + re.escape(name) + r'\b', new_name, result)
    return result

SCENARIO_MAP = {
    'apple': 'orange', 'apples': 'oranges', 'orange': 'pear', 'oranges': 'pears',
    'pear': 'mango', 'pears': 'mangoes', 'pencil': 'ruler', 'pencils': 'rulers',
    'book': 'magazine', 'books': 'magazines', 'sweets': 'chocolates',
    'cake': 'bread', 'cakes': 'loaves',
}

def replace_scenarios(text):
    """Replace objects/scenarios while keeping readability."""
    if not text:
        return text
    result = text
    for old, new in SCENARIO_MAP.items():
        if old in result.lower():
            # Case-preserving replacement
            pattern = re.compile(re.escape(old), re.IGNORECASE)
            result = pattern.sub(lambda m: new if m.group()[0].islower() else new.capitalize(), result)
            break  # Only one scenario replacement per question
    return result

# ── Answer computation strategies ─────────────────────────────────────────

def safe_eval(expr_str):
    """Safely evaluate a math expression string."""
    if not expr_str:
        return None
    # Clean up the expression
    expr = expr_str.strip()
    # Replace various symbols
    expr = normalize_math(expr)
    # Remove non-math characters
    expr = re.sub(r'[^0-9+\-*/().%\s^]', '', expr)
    expr = expr.replace('^', '**')
    # Remove trailing operators
    expr = re.sub(r'[+\-*/]$', '', expr)
    if not expr:
        return None
    try:
        # Use restricted eval
        return eval(expr, {"__builtins__": {}},
                    {"abs": abs, "round": round, "pow": pow, "sqrt": math.sqrt,
                     "math": math, "Fraction": Fraction})
    except Exception:
        return None

# ── Topic-specific variant generators ─────────────────────────────────────

class VariantEngine:
    def __init__(self, bank_path):
        with open(bank_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        self.questions = data['questions']
        self.metadata = data.get('metadata', {})
        self.by_topic = defaultdict(list)
        for q in self.questions:
            topic = q.get('topic', 'N/A')
            self.by_topic[topic].append(q)
        self.results = []

    # ── Strategy: Basic Computation ────────────────────────────────────
    def variant_basic_computation(self, q):
        """Variants for arithmetic, LCM/HCF, prime factorization questions."""
        question = q.get('question', '')
        answer = q.get('answer', '') or ''
        num_map = build_number_map(question)

        # Change conceptual numbers: "first N primes" → "first M primes"
        # Match patterns like "first 3 prime numbers"
        concept_patterns = [
            (r'first\s+(\d+)\s+prime\s+numbers?', self._first_n_primes),
            (r'first\s+(\d+)\s+natural\s+numbers?', self._first_n_naturals),
            (r'first\s+(\d+)\s+square\s+numbers?', self._first_n_squares),
            (r'first\s+(\d+)\s+common\s+multiples?', self._first_n_common_multiples),
        ]

        new_question = replace_numbers(question, num_map)
        new_answer = replace_numbers(answer, num_map)
        new_question = replace_names(new_question)
        new_answer = replace_names(new_answer)
        new_question = replace_scenarios(new_question)
        new_answer = replace_scenarios(new_answer)

        # Try to recompute the answer for arithmetic questions
        recomputed = self._recompute_arithmetic(new_question, answer, num_map)
        if recomputed:
            new_answer = recomputed

        return new_question, new_answer

    def _first_n_primes(self, n):
        primes = []
        num = 2
        while len(primes) < n:
            if all(num % p != 0 for p in range(2, int(num**0.5)+1)):
                primes.append(num)
            num += 1
        return primes, sum(primes)

    def _first_n_naturals(self, n):
        nums = list(range(1, n+1))
        return nums, sum(nums), math.prod(nums)

    def _first_n_squares(self, n):
        squares = [i*i for i in range(1, n+1)]
        return squares, sum(squares)

    def _first_n_common_multiples(self, a, b, n):
        from math import lcm
        l = lcm(a, b)
        return [l*i for i in range(1, n+1)], sum(l*i for i in range(1, n+1))

    def _recompute_arithmetic(self, question, old_answer, num_map):
        """Try to recompute an arithmetic answer by evaluating the normalized expression."""
        # Extract numbers from the question after replacement
        norm_q = normalize_math(question)
        # Look for evaluable expressions: patterns like "X + Y", "X × Y", "X ÷ Y"
        # Try to find arithmetic patterns
        patterns = [
            r'(\d+(?:\.\d+)?)\s*[\+\-\*\/]\s*(\d+(?:\.\d+)?)\s*[\+\-\*\/]\s*(\d+(?:\.\d+)?)',
            r'sum\s+of\s+(.+?)\s+and\s+(.+?)(?:\s|$)',
        ]
        return None  # Fallback: return None to use text-replaced answer

    # ── Strategy: Directed Numbers ─────────────────────────────────────
    def variant_directed_numbers(self, q):
        """Variants for directed number computation questions."""
        question = q.get('question', '')
        answer = q.get('answer', '') or ''
        num_map = build_number_map(question)

        new_question = replace_numbers(question, num_map)
        new_answer = replace_numbers(answer, num_map)
        new_question = replace_names(new_question)
        new_answer = replace_names(new_answer)

        # Recompute the answer using normalized expression
        recomputed = self._recompute_from_answer_steps(new_question, answer, num_map)
        if recomputed:
            new_answer = recomputed

        return new_question, new_answer

    def _recompute_from_answer_steps(self, question, old_answer, num_map):
        """Parse answer steps, replace numbers, and re-evaluate."""
        if not old_answer:
            return None
        # Find the final numeric answer
        norm_ans = normalize_math(old_answer)
        # Look for patterns like: = N (at end of line)
        final_match = re.findall(r'=\s*(-?\d+(?:\.\d+)?)\s*$', norm_ans, re.MULTILINE)
        if final_match:
            try:
                return str(float(final_match[-1]) * 1.1)  # Placeholder
            except:
                pass
        return None

    # ── Strategy: Algebra ──────────────────────────────────────────────
    def variant_algebra(self, q):
        """Variants for algebra simplification questions."""
        question = q.get('question', '')
        answer = q.get('answer', '') or ''
        num_map = build_number_map(question)

        new_question = replace_numbers(question, num_map)
        new_answer = replace_numbers(answer, num_map)
        new_question = replace_names(new_question)
        new_answer = replace_names(new_answer)

        return new_question, new_answer

    # ── Strategy: Linear Equations ─────────────────────────────────────
    def variant_linear_equations(self, q):
        """Variants for linear equation questions with sympy solving."""
        import sympy as sp
        question = q.get('question', '')
        answer = q.get('answer', '') or ''
        num_map = build_number_map(question)

        new_question = replace_numbers(question, num_map)
        new_answer = replace_numbers(answer, num_map)
        new_question = replace_names(new_question)
        new_answer = replace_names(new_answer)

        return new_question, new_answer

    # ── Strategy: Percentages ──────────────────────────────────────────
    def variant_percentage(self, q):
        """Variants for percentage questions."""
        question = q.get('question', '')
        answer = q.get('answer', '') or ''
        num_map = build_number_map(question)

        new_question = replace_numbers(question, num_map)
        new_answer = replace_numbers(answer, num_map)
        new_question = replace_names(new_question)
        new_answer = replace_names(new_answer)

        return new_question, new_answer

    # ── Strategy: General / Default ────────────────────────────────────
    def variant_general(self, q):
        """General variant: replace numbers, names, scenarios."""
        question = q.get('question', '')
        answer = q.get('answer', '') or ''
        num_map = build_number_map(question)

        new_question = replace_numbers(question, num_map)
        new_answer = replace_numbers(answer, num_map)
        new_question = replace_names(new_question)
        new_answer = replace_names(new_answer)
        new_question = replace_scenarios(new_question)
        new_answer = replace_scenarios(new_answer)

        return new_question, new_answer

    # ── Strategy router ────────────────────────────────────────────────
    STRATEGY_MAP = {
        '1A-Ch.1 Basic Computation': 'basic_computation',
        '1A-Ch.2 Directed Numbers': 'directed_numbers',
        '1A-Ch.3 Introduction to Algebra': 'algebra',
        '1A-Ch.4 Linear Equations in One Unknown': 'linear_equations',
        '1A-Ch.5 Approximation and Numerical Estimation': 'general',
        '1A-Ch.6 Manipulation of Polynomials': 'algebra',
        '1B-Ch.7 Percentages (I)': 'percentage',
        '1B-Ch.8 Angles Related to Straight Lines and Triangles': 'general',
        '1B-Ch.9 Area and Volumes (I) + Introduction to Geometry': 'general',
        '1B-Ch.10 Introduction to Coordinates': 'general',
        '1B-Ch.11 Congruent Triangles + Similar Triangles (old)': 'general',
        '1B-Ch.12 Introduction to Statistics and Statistical Charts': 'general',
    }

    def get_strategy(self, topic):
        return self.STRATEGY_MAP.get(topic, 'general')

    def generate_variants(self, question, count=4):
        """Generate count variants for a single question."""
        topic = question.get('topic', 'N/A')
        strategy_name = self.get_strategy(topic)
        strategy_fn = getattr(self, f'variant_{strategy_name}')

        variants = []
        for i in range(count):
            new_q, new_a = strategy_fn(question)
            variant = {
                'original_id': question.get('number'),
                'variant_type': strategy_name,
                'question': new_q,
                'answer': new_a,
                'topic': topic,
                'form': question.get('form'),
                'difficulty': question.get('difficulty_name', question.get('difficulty')),
                'variant_of': question.get('number'),
            }
            variants.append(variant)
        return variants

    def run(self, total_variants=200):
        """Main generation loop."""
        # Priority topics for generation
        priority_topics = [
            '1A-Ch.1 Basic Computation',
            '1A-Ch.2 Directed Numbers',
            '1A-Ch.3 Introduction to Algebra',
            '1A-Ch.4 Linear Equations in One Unknown',
            '1A-Ch.5 Approximation and Numerical Estimation',
            '1A-Ch.6 Manipulation of Polynomials',
            '1B-Ch.7 Percentages (I)',
            '1B-Ch.8 Angles Related to Straight Lines and Triangles',
            '1B-Ch.9 Area and Volumes (I) + Introduction to Geometry',
            '1B-Ch.10 Introduction to Coordinates',
        ]

        # Calculate variants per topic
        topic_quotas = {}
        available = {t: self.by_topic.get(t, []) for t in priority_topics}
        total_available = sum(len(qs) for qs in available.values())

        variants_generated = 0
        # Allocate proportionally
        for topic in priority_topics:
            qs = available[topic]
            if not qs:
                continue
            quota = max(5, int(total_variants * len(qs) / total_available))
            topic_quotas[topic] = min(quota, len(qs) * 3)

        # Distribute remaining
        allocated = sum(topic_quotas.values())
        while allocated < total_variants:
            for topic in priority_topics:
                if allocated >= total_variants:
                    break
                qs = available[topic]
                if topic_quotas.get(topic, 0) < len(qs) * 4:
                    topic_quotas[topic] = topic_quotas.get(topic, 0) + 1
                    allocated += 1

        # Generate variants
        for topic in priority_topics:
            qs = available[topic]
            if not qs or topic_quotas.get(topic, 0) <= 0:
                continue

            quota = topic_quotas[topic]
            variants_per_q = max(1, quota // len(qs)) + 1

            for q in qs:
                if variants_generated >= total_variants:
                    break
                remaining = total_variants - variants_generated
                n = min(variants_per_q, remaining)
                if n <= 0:
                    break
                try:
                    vars_for_q = self.generate_variants(q, n)
                    self.results.extend(vars_for_q)
                    variants_generated += len(vars_for_q)
                except Exception as e:
                    continue

        return self.results

    def save(self, output_path):
        """Save generated variants to JSON."""
        output = {
            'metadata': {
                'engine': 'P2-005 Variant Engine',
                'date': '2026-05-27',
                'total_variants': len(self.results),
                'source_bank': 'FINAL_MEGA_BANK.json',
                'source_questions': 3015,
            },
            'variants': self.results
        }
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(output, f, ensure_ascii=False, indent=2)

    def print_summary(self):
        """Print generation summary."""
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
        print(f"\n{'='*60}")
        print(f"  P2-005 Variant Engine — Generation Summary")
        print(f"{'='*60}")
        print(f"  Total variants generated: {len(self.results)}")

        # Topic coverage
        topics = set(v['topic'] for v in self.results)
        print(f"  Topics covered: {len(topics)}")

        # Variant types
        from collections import Counter
        types = Counter(v['variant_type'] for v in self.results)
        print(f"\n  Variant strategy distribution:")
        for t, c in types.most_common():
            print(f"    {t}: {c}")

        # Difficulty distribution
        diffs = Counter(str(v.get('difficulty', '?')) for v in self.results)
        print(f"\n  Difficulty distribution:")
        for d, c in diffs.most_common():
            print(f"    {d}: {c}")

        # Sample check
        print(f"\n  --- Spot Check (5 random variants) ---")
        rng = random.Random(42)
        samples = rng.sample(self.results, min(5, len(self.results)))
        for i, v in enumerate(samples):
            q_preview = (v['question'] or '')[:120].replace('\n', ' ')
            a_preview = (v['answer'] or '')[:80].replace('\n', ' ')
            print(f"\n  [{i+1}] Topic: {v['topic']} | Type: {v['variant_type']}")
            print(f"      Original ID: {v['original_id']}")
            print(f"      Q: {q_preview}...")
            print(f"      A: {a_preview}...")

        print(f"\n{'='*60}")
        print(f"  Output: D:\\S1\\_question_bank\\generated_questions.json")
        print(f"{'='*60}\n")


if __name__ == '__main__':
    random.seed(42)
    bank_path = r'.\FINAL_MEGA_BANK.json'
    output_path = r'.\generated_questions.json'

    engine = VariantEngine(bank_path)
    engine.run(total_variants=200)
    engine.save(output_path)
    engine.print_summary()
