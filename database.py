import sqlite3

DB_FILE = "jobs.db"  # SQLite database file


def get_connection():
    """Open a connection to the SQLite database."""
    return sqlite3.connect(DB_FILE, check_same_thread=False)


def create_table():
    """Create the applications table if it doesn't already exist."""
    conn = get_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS applications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company TEXT NOT NULL,
            role TEXT NOT NULL,
            salary TEXT,
            stage TEXT NOT NULL,
            applied_on TEXT NOT NULL,
            link TEXT
        )
    """)
    conn.commit()
    conn.close()


def add_application(company, role, salary, stage, applied_on, link):
    """Insert a new application record."""
    conn = get_connection()
    conn.execute(
        "INSERT INTO applications (company, role, salary, stage, applied_on, link) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (company, role, salary, stage, applied_on, link),
    )
    conn.commit()
    conn.close()


def get_all_applications(stage_filter=None, search=None):
    """Return applications, most recently added first.

    stage_filter: only return rows with this exact stage (None/"All" = no filter)
    search: case-insensitive substring match on company or role (None/"" = no filter)
    """
    conn = get_connection()
    query = "SELECT id, company, role, salary, stage, applied_on, link FROM applications"
    conditions = []
    params = []

    if stage_filter and stage_filter != "All":
        conditions.append("stage = ?")
        params.append(stage_filter)

    if search:
        conditions.append("(company LIKE ? OR role LIKE ?)")
        like_term = f"%{search}%"
        params.extend([like_term, like_term])

    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY id DESC"

    cursor = conn.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    return rows


def get_stats():
    """Return dashboard stats: total, interviews, offers, response rate (%).

    Response rate = applications currently at OA, Interview, or Offer,
    divided by total applications (based on current stage).
    """
    conn = get_connection()
    total = conn.execute("SELECT COUNT(*) FROM applications").fetchone()[0]
    interviews = conn.execute(
        "SELECT COUNT(*) FROM applications WHERE stage = 'Interview'"
    ).fetchone()[0]
    offers = conn.execute(
        "SELECT COUNT(*) FROM applications WHERE stage = 'Offer'"
    ).fetchone()[0]
    responded = conn.execute(
        "SELECT COUNT(*) FROM applications WHERE stage IN ('OA', 'Interview', 'Offer')"
    ).fetchone()[0]
    conn.close()

    response_rate = (responded / total * 100) if total > 0 else 0
    return {
        "total": total,
        "interviews": interviews,
        "offers": offers,
        "response_rate": round(response_rate, 1),
    }


def update_stage(app_id, new_stage):
    """Update the stage of a single application by id."""
    conn = get_connection()
    conn.execute(
        "UPDATE applications SET stage = ? WHERE id = ?", (new_stage, app_id)
    )
    conn.commit()
    conn.close()


def delete_application(app_id):
    """Delete a single application by id."""
    conn = get_connection()
    conn.execute("DELETE FROM applications WHERE id = ?", (app_id,))
    conn.commit()
    conn.close()