import json, os, psycopg2, sys
from pathlib import Path

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://postgres:@localhost:5432/question_bank")

def connect():
    print(f"Connecting to DB...")
    return psycopg2.connect(DATABASE_URL)

def create_tables(conn):
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS questions (
            id SERIAL PRIMARY KEY,
            source TEXT,
            school TEXT,
            year TEXT,
            level TEXT,
            topic TEXT,
            chapter TEXT,
            subtopic TEXT,
            question_type TEXT,
            question_text TEXT,
            answer TEXT,
            marks INTEGER,
            tags TEXT,
            created_at TIMESTAMP DEFAULT NOW()
        );
        CREATE INDEX IF NOT EXISTS idx_questions_topic ON questions(topic);
        CREATE INDEX IF NOT EXISTS idx_questions_level ON questions(level);
    """)
    conn.commit()
    print("Tables created")

def import_questions(conn):
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM questions")
    count = cur.fetchone()[0]
    if count > 0:
        print(f"DB has {count} questions, skipping import")
        return
    
    src = Path("question_bank_export.json")
    if not src.exists():
        print("WARNING: question_bank_export.json not found. Starting empty.")
        return
    
    print(f"Importing from {src} ({src.stat().st_size}B)...")
    data = json.loads(src.read_text(encoding="utf-8"))
    questions = data.get("questions", [])
    
    for q in questions:
        cur.execute("""
            INSERT INTO questions (source, school, year, level, topic, question_text, answer, marks)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            str(q.get("source", q.get("school", "")))[:100],
            str(q.get("school", ""))[:100],
            str(q.get("year", ""))[:20],
            str(q.get("level", q.get("form", "")))[:20],
            str(q.get("topic", q.get("ch", "")))[:100],
            str(q.get("question", q.get("question_text", "")))[:5000],
            str(q.get("answer", ""))[:2000],
            int(q.get("marks", 0)) if q.get("marks") else 0
        ))
        if cur.rowcount % 500 == 0:
            print(f"  {cur.rowcount}...")
    
    conn.commit()
    print(f"Imported {len(questions)} questions")

if __name__ == "__main__":
    conn = connect()
    try:
        create_tables(conn)
        import_questions(conn)
        print("Migration complete!")
    finally:
        conn.close()
