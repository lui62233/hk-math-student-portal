"""Gamification engine — points, badges, streaks, leaderboard, daily challenges."""
from datetime import date

BADGE_THRESHOLDS = [
    (0, "Bronze"),
    (100, "Silver"),
    (300, "Gold"),
    (600, "Platinum"),
    (1000, "Diamond"),
]

STREAK_MILESTONE = 5
STREAK_BONUS = 10
DAILY_BONUS = 25
DAILY_TARGET = 5


def get_badge(points: int) -> str:
    badge = "Bronze"
    for threshold, name in BADGE_THRESHOLDS:
        if points >= threshold:
            badge = name
    return badge


def ensure_table(conn):
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS gamification (
            student_name TEXT PRIMARY KEY,
            points INT DEFAULT 0,
            streak INT DEFAULT 0,
            badge TEXT DEFAULT 'Bronze',
            last_played DATE,
            daily_date DATE,
            daily_correct INT DEFAULT 0,
            daily_bonus_claimed BOOLEAN DEFAULT FALSE
        )
    """)
    conn.commit()
    cur.close()


def get_gamification(conn, student_name: str) -> dict | None:
    cur = conn.cursor()
    cur.execute(
        """SELECT student_name, points, streak, badge, last_played,
                  daily_date, daily_correct, daily_bonus_claimed
           FROM gamification WHERE student_name = %s""",
        (student_name,),
    )
    row = cur.fetchone()
    cur.close()
    if not row:
        return None
    return {
        "student_name": row[0],
        "points": row[1],
        "streak": row[2],
        "badge": row[3],
        "last_played": str(row[4]) if row[4] else None,
        "daily_date": str(row[5]) if row[5] else None,
        "daily_correct": row[6],
        "daily_bonus_claimed": row[7],
    }


def update_gamification(conn, student_name: str, score: float, max_score: float,
                        status: str, is_daily: bool = False) -> dict:
    """Update points, streak, and badge after an answer. Returns delta + new state."""
    today = date.today()
    cur = conn.cursor()

    cur.execute(
        """SELECT points, streak, last_played, daily_date, daily_correct, daily_bonus_claimed
           FROM gamification WHERE student_name = %s""",
        (student_name,),
    )
    row = cur.fetchone()

    if row:
        points, streak, last_played, daily_date, daily_correct, daily_bonus_claimed = row
    else:
        points, streak, last_played, daily_date, daily_correct, daily_bonus_claimed = 0, 0, None, None, 0, False

    # --- points earned this answer ---
    if status == "CORRECT":
        earned = 10
        streak += 1
    elif status == "PARTIAL":
        earned = 5
        streak = 0
    else:
        earned = 0
        streak = 0

    bonus = 0

    # Streak milestone bonus
    if streak > 0 and streak % STREAK_MILESTONE == 0:
        bonus += STREAK_BONUS

    # Daily challenge tracking
    is_new_day = str(daily_date) != str(today)
    if is_new_day:
        daily_correct = 0
        daily_bonus_claimed = False
        daily_date = str(today)

    if is_daily and status == "CORRECT":
        daily_correct += 1

    if is_daily and daily_correct >= DAILY_TARGET and not daily_bonus_claimed:
        bonus += DAILY_BONUS
        daily_bonus_claimed = True

    points += earned + bonus
    badge = get_badge(points)

    cur.execute(
        """INSERT INTO gamification
               (student_name, points, streak, badge, last_played,
                daily_date, daily_correct, daily_bonus_claimed)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
           ON CONFLICT (student_name) DO UPDATE SET
               points = EXCLUDED.points,
               streak = EXCLUDED.streak,
               badge = EXCLUDED.badge,
               last_played = EXCLUDED.last_played,
               daily_date = EXCLUDED.daily_date,
               daily_correct = EXCLUDED.daily_correct,
               daily_bonus_claimed = EXCLUDED.daily_bonus_claimed""",
        (student_name, points, streak, badge, today,
         daily_date, daily_correct, daily_bonus_claimed),
    )
    conn.commit()
    cur.close()

    return {
        "student_name": student_name,
        "points": points,
        "streak": streak,
        "badge": badge,
        "earned": earned,
        "bonus": bonus,
        "daily_correct": daily_correct,
        "daily_target": DAILY_TARGET,
        "daily_bonus_claimed": daily_bonus_claimed,
    }


def get_leaderboard(conn, limit: int = 10) -> list[dict]:
    cur = conn.cursor()
    cur.execute(
        """SELECT student_name, points, streak, badge
           FROM gamification ORDER BY points DESC LIMIT %s""",
        (limit,),
    )
    rows = cur.fetchall()
    cur.close()
    return [
        {"rank": i + 1, "student_name": r[0], "points": r[1],
         "streak": r[2], "badge": r[3]}
        for i, r in enumerate(rows)
    ]
