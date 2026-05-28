#!/usr/bin/env python3
"""AI Paper Quality Scorer — scores generated exam papers across 5 dimensions using frellmapi."""

import json
import os
import re
import sys
import urllib.request

FRELLM_URL = "http://localhost:3001/v1/chat/completions"
FRELLM_KEY = "freellmapi-a4fc69d7fa5ca8504930131b70d7b0cfdf6d0b09abe941ce"
MODEL = "openai/gpt-oss-20b:free"
EXAMS_DIR = r"D:\S1\_generated_papers\exams"
BANK_PATH = r".\unified_question_bank_v3.json"

HK_S1_TOPICS = [
    "1A-Ch.1 Basic Computation",
    "1A-Ch.2 Directed Numbers",
    "1A-Ch.3 Introduction to Algebra",
    "1A-Ch.4 Linear Equations in One Unknown",
    "1A-Ch.5 Approximation and Numerical Estimation",
    "1A-Ch.6 Manipulation of Polynomials",
    "1B-Ch.7 Percentages (I)",
    "1B-Ch.8 Angles Related to Straight Lines and Triangles",
    "1B-Ch.9 Area and Volumes (I) + Introduction to Geometry",
    "1B-Ch.10 Introduction to Coordinates",
    "1B-Ch.11 Congruent Triangles + Similar Triangles (old)",
    "1B-Ch.12 Introduction to Statistics and Statistical Charts",
]


def _call_frellm(prompt: str, max_tokens: int = 300) -> str:
    data = json.dumps({
        "model": MODEL,
        "messages": [
            {"role": "system", "content": "You are an expert HK mathematics exam evaluator. Respond with ONLY the requested JSON. No markdown, no explanation."},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": max_tokens,
        "temperature": 0.3,
    }).encode()
    req = urllib.request.Request(FRELLM_URL, data=data, headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {FRELLM_KEY}",
    })
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = json.loads(resp.read())
            return body["choices"][0]["message"]["content"]
    except Exception as e:
        return json.dumps({"error": str(e)})


class AIQualityScorer:
    def __init__(self, exams_dir: str = EXAMS_DIR, bank_path: str = BANK_PATH):
        self.exams_dir = exams_dir
        self.bank_path = bank_path
        self._bank_topics = None

    def _load_bank_topics(self) -> list[str]:
        if self._bank_topics:
            return self._bank_topics
        try:
            with open(self.bank_path, encoding="utf-8") as f:
                bank = json.load(f)
            topics = set()
            for q in bank.get("questions", []):
                t = q.get("topic", "")
                if t:
                    topics.add(t)
            self._bank_topics = sorted(topics)
        except Exception:
            self._bank_topics = HK_S1_TOPICS
        return self._bank_topics

    def _find_paper(self, paper_id: str) -> str | None:
        if paper_id == "latest":
            papers = sorted(
                [f for f in os.listdir(self.exams_dir) if f.endswith(".tex")],
                key=lambda x: os.path.getmtime(os.path.join(self.exams_dir, x)),
                reverse=True,
            )
            return os.path.join(self.exams_dir, papers[0]) if papers else None
        if os.path.isfile(paper_id):
            return paper_id
        path = os.path.join(self.exams_dir, paper_id)
        if os.path.isfile(path):
            return path
        if not paper_id.endswith(".tex"):
            path = os.path.join(self.exams_dir, paper_id + ".tex")
            if os.path.isfile(path):
                return path
        return None

    def parse_paper(self, paper_path: str) -> dict:
        with open(paper_path, encoding="utf-8") as f:
            text = f.read()

        form_match = re.search(r"Form\s+(\d)", text)
        form = int(form_match.group(1)) if form_match else 1

        school_match = re.search(r"\\rhead\{([^}]+)\}", text)
        school = school_match.group(1) if school_match else "Unknown"

        title_match = re.search(r"\\textbf\{([^}]+)\}[^}]*\}[^{]*\\end\{center\}", text[:2000])
        if not title_match:
            title_match = re.search(r"\\textbf\{([^}]+)\}", text[300:1500])
        title = title_match.group(1).strip() if title_match else "Unknown"

        total_marks = 0
        marks_match = re.search(r"Total\s+Marks?:\s*(\d+)", text)
        if marks_match:
            total_marks = int(marks_match.group(1))

        questions = []
        for m in re.finditer(
            r"\\textbf\{(\d+)\.\}?\s*(.*?)(?=\\textbf\{\d+\.\}|\\vfill|\\end\{document\})",
            text, re.DOTALL,
        ):
            qnum = m.group(1)
            qbody = m.group(2).strip()

            marks = 0
            mk = re.search(r"\((\d+)\s*(?:marks?|分)\)", qbody)
            if mk:
                marks = int(mk.group(1))

            qtype = "CQ"
            if re.search(r"\\begin\{multicols\}|\\textbf\{[A-E]\.\}", qbody):
                qtype = "MC"
            if re.search(r"word\s+problem|story|context|scenario", qbody, re.IGNORECASE):
                qtype = "WP"

            has_answer = bool(re.search(r"\\textcolor\{blue\}", qbody))
            answer_text = ""
            if has_answer:
                ans_parts = re.findall(r"\\textcolor\{blue\}\{([^}]+(?:\{[^}]*\}[^}]*)*)\}", qbody)
                answer_text = " ".join(ans_parts)

            in_diagram = "\\includegraphics" in qbody

            questions.append({
                "number": qnum,
                "type": qtype,
                "marks": marks,
                "has_answer": has_answer,
                "answer_preview": answer_text[:200] if answer_text else "",
                "has_diagram": in_diagram,
                "text_preview": re.sub(r"\\[a-zA-Z]+(\{[^}]*\})*", "", qbody)[:200].strip(),
            })

        question_count = len(questions)
        if question_count == 0:
            questions = self._fallback_parse(text)

        mc_count = sum(1 for q in questions if q["type"] == "MC")
        cq_count = sum(1 for q in questions if q["type"] == "CQ")
        wp_count = sum(1 for q in questions if q["type"] == "WP")
        with_answers = sum(1 for q in questions if q["has_answer"])
        with_diagrams = sum(1 for q in questions if q["has_diagram"])
        total_marks_parsed = sum(q["marks"] for q in questions) or total_marks

        is_marking_scheme = "MARKING SCHEME" in text or "marking scheme" in text.lower()

        return {
            "path": paper_path,
            "filename": os.path.basename(paper_path),
            "school": school,
            "form": form,
            "title": title,
            "total_marks": total_marks_parsed,
            "question_count": question_count,
            "is_marking_scheme": is_marking_scheme,
            "mc_count": mc_count,
            "cq_count": cq_count,
            "wp_count": wp_count,
            "with_answers": with_answers,
            "with_diagrams": with_diagrams,
            "questions": questions,
        }

    def _fallback_parse(self, text: str) -> list[dict]:
        questions = []
        for m in re.finditer(r"\\(?:textbf|item)\s*\{(\d+)\.?\}?\s*(.*?)(?=\\(?:textbf|item)\s*\{|$)", text, re.DOTALL):
            qnum = m.group(1)
            qbody = m.group(2).strip()
            if len(qbody) < 20:
                continue
            questions.append({
                "number": qnum, "type": "CQ", "marks": 0,
                "has_answer": "blue" in qbody, "answer_preview": "",
                "has_diagram": "includegraphics" in qbody,
                "text_preview": qbody[:200],
            })
        return questions

    def score_paper(self, paper_id: str = "latest") -> dict:
        paper_path = self._find_paper(paper_id)
        if not paper_path:
            return {"error": f"Paper not found: {paper_id}"}

        paper = self.parse_paper(paper_path)
        bank_topics = self._load_bank_topics()
        dimensions = self._score_all_dimensions(paper, bank_topics)

        raw_total = sum(d["score"] for d in dimensions.values())
        overall = round(raw_total / 5 * 10)  # 5 dims x 1-10 = max 50 -> scale to 100

        return {
            "paper": paper["filename"],
            "title": paper["title"],
            "school": paper["school"],
            "form": paper["form"],
            "question_count": paper["question_count"],
            "total_marks": paper["total_marks"],
            "is_marking_scheme": paper["is_marking_scheme"],
            "breakdown": {
                "mc_count": paper["mc_count"],
                "cq_count": paper["cq_count"],
                "wp_count": paper["wp_count"],
                "with_answers": paper["with_answers"],
                "with_diagrams": paper["with_diagrams"],
            },
            "dimensions": {k: v["score"] for k, v in dimensions.items()},
            "dimension_details": {k: v["reasoning"] for k, v in dimensions.items()},
            "overall_score": overall,
            "raw_total": raw_total,
            "max_raw": 50,
        }

    def _score_all_dimensions(self, paper: dict, bank_topics: list[str]) -> dict:
        summary = self._build_summary(paper)
        results = {}

        for dim, prompt in [
            ("coverage", self._coverage_prompt(summary, bank_topics)),
            ("difficulty_balance", self._difficulty_prompt(summary)),
            ("question_variety", self._variety_prompt(summary)),
            ("answer_accuracy", self._accuracy_prompt(summary)),
            ("curriculum_alignment", self._alignment_prompt(summary)),
        ]:
            resp = _call_frellm(prompt)
            parsed = self._parse_dimension_response(resp)
            results[dim] = parsed

        return results

    def _build_summary(self, paper: dict) -> str:
        lines = [
            f"Paper: {paper['title']}",
            f"School: {paper['school']}, Form: {paper['form']}",
            f"Questions: {paper['question_count']}, Total Marks: {paper['total_marks']}",
            f"MC: {paper['mc_count']}, CQ: {paper['cq_count']}, Word Problems: {paper['wp_count']}",
            f"Has Answers: {paper['with_answers']}/{paper['question_count']}",
            f"Has Diagrams: {paper['with_diagrams']}/{paper['question_count']}",
            f"Is Marking Scheme: {paper['is_marking_scheme']}",
            "",
            "Question previews:",
        ]
        for q in paper["questions"][:15]:
            lines.append(f"  Q{q['number']} [{q['type']}] ({q['marks']}m): {q['text_preview'][:100]}")
            if q["answer_preview"]:
                lines.append(f"    Answer: {q['answer_preview'][:100]}")
        return "\n".join(lines)

    def _coverage_prompt(self, summary: str, topics: list[str]) -> str:
        return f"""Rate this exam paper on topic COVERAGE (1-10).

HK S1/S2 curriculum topics:
{chr(10).join(f'- {t}' for t in topics)}

Paper summary:
{summary}

How many different curriculum topics does this paper cover?
1-3 = narrow (1-3 topics), 4-6 = moderate (4-7 topics), 7-10 = broad (8+ topics).

Return JSON: {{"score": <1-10>, "reasoning": "<1-2 sentences>"}}"""

    def _difficulty_prompt(self, summary: str) -> str:
        return f"""Rate this exam paper on DIFFICULTY BALANCE (1-10).

Paper summary:
{summary}

Consider:
- Mix of straightforward vs challenging questions
- Marks distribution (higher marks = harder questions)
- Whether it has both basic computation AND multi-step problems
- 1-3 = all easy or all hard, 4-6 = some mix, 7-10 = well-balanced

Return JSON: {{"score": <1-10>, "reasoning": "<1-2 sentences>"}}"""

    def _variety_prompt(self, summary: str) -> str:
        return f"""Rate this exam paper on QUESTION VARIETY (1-10).

Paper summary:
{summary}

Consider:
- Mix of MC, CQ, and word problems
- Different mathematical skills tested (computation, proof, application, reasoning)
- Presence of diagrams/visual elements
- 1-3 = all same type, 4-6 = 2 types, 7-10 = 3+ types with good mix

Return JSON: {{"score": <1-10>, "reasoning": "<1-2 sentences>"}}"""

    def _accuracy_prompt(self, summary: str) -> str:
        return f"""Rate this exam paper on ANSWER ACCURACY (1-10).

Paper summary:
{summary}

Consider:
- Are answers provided for questions?
- Do the answers appear mathematically correct?
- Are marking schemes included?
- 1-3 = no/mostly wrong answers, 4-6 = partial answers, 7-10 = complete accurate answers

Return JSON: {{"score": <1-10>, "reasoning": "<1-2 sentences>"}}"""

    def _alignment_prompt(self, summary: str) -> str:
        return f"""Rate this exam paper on CURRICULUM ALIGNMENT (1-10).

Paper summary:
{summary}

HK S1/S2 curriculum should cover: Basic Computation, Directed Numbers, Algebra, Linear Equations, Approximation, Polynomials, Percentages, Angles/Triangles, Area/Volumes, Coordinates, Congruence/Similarity, Statistics.

Consider:
- Do the questions match the expected form level?
- Are topics appropriate for the stated form?
- 1-3 = off-curriculum/too advanced, 4-6 = partially aligned, 7-10 = exactly aligned

Return JSON: {{"score": <1-10>, "reasoning": "<1-2 sentences>"}}"""

    def _parse_dimension_response(self, text: str) -> dict:
        # Strip markdown code fences
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.MULTILINE).strip()
        try:
            data = json.loads(cleaned)
            score = int(data.get("score", 5))
            return {"score": max(1, min(10, score)), "reasoning": data.get("reasoning", "")}
        except (json.JSONDecodeError, ValueError):
            pass
        # Fallback: extract score and reasoning with regex
        m = re.search(r'"score"\s*:\s*(\d+)', text)
        score = int(m.group(1)) if m else 5
        m2 = re.search(r'"reasoning"\s*:\s*"([^"]*(?:\\.[^"]*)*)"', text)
        reasoning = m2.group(1) if m2 else f"Raw: {text[:120]}"
        return {"score": max(1, min(10, score)), "reasoning": reasoning}


if __name__ == "__main__":
    scorer = AIQualityScorer()

    if "--test" in sys.argv:
        test_papers = [
            "a_20260527_220332.tex",
            "f2_q_20260527_230608.tex",
            "mc_f1_20260527_233950.tex",
        ]
        for tp in test_papers:
            print(f"\n{'='*60}")
            result = scorer.score_paper(tp)
            print(json.dumps(result, indent=2, ensure_ascii=False))
        print("\nDone.")
    else:
        paper_id = sys.argv[1] if len(sys.argv) > 1 else "latest"
        result = scorer.score_paper(paper_id)
        print(json.dumps(result, indent=2, ensure_ascii=False))

