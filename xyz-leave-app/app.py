import os
import sqlite3
from datetime import date
from functools import wraps

from flask import (Flask, render_template, request, redirect,
                   url_for, session, flash, g)
from werkzeug.security import generate_password_hash, check_password_hash

COMPANY = "XYZ"
DB_PATH = os.environ.get("DB_PATH", "leave.db")

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-me-in-production")


# ---------- Database ----------
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(exc):
    db = g.pop("db", None)
    if db:
        db.close()


def init_db():
    db = sqlite3.connect(DB_PATH)
    db.executescript("""
    CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        full_name TEXT NOT NULL,
        role TEXT NOT NULL CHECK(role IN ('admin','employee'))
    );
    CREATE TABLE IF NOT EXISTS leaves(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL REFERENCES users(id),
        leave_type TEXT NOT NULL,
        start_date TEXT NOT NULL,
        end_date TEXT NOT NULL,
        reason TEXT,
        status TEXT NOT NULL DEFAULT 'Pending',
        applied_on TEXT NOT NULL,
        decided_by TEXT
    );
    """)
    if db.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0:
        seed = [("admin", "admin123", "Admin (XYZ)", "admin"),
                ("user1", "user123", "User One", "employee"),
                ("user2", "user123", "User Two", "employee")]
        for u, p, n, r in seed:
            db.execute("INSERT INTO users(username,password_hash,full_name,role) VALUES(?,?,?,?)",
                       (u, generate_password_hash(p), n, r))
    db.commit()
    db.close()


# ---------- Auth helpers ----------
def login_required(role=None):
    def deco(f):
        @wraps(f)
        def wrapper(*a, **kw):
            if "user_id" not in session:
                return redirect(url_for("login"))
            if role and session.get("role") != role:
                flash("You are not allowed to view that page.", "danger")
                return redirect(url_for("dashboard"))
            return f(*a, **kw)
        return wrapper
    return deco


@app.context_processor
def inject():
    return dict(company=COMPANY)


# ---------- Routes ----------
@app.route("/")
def index():
    return redirect(url_for("dashboard" if "user_id" in session else "login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        user = get_db().execute("SELECT * FROM users WHERE username=?",
                                (request.form["username"].strip(),)).fetchone()
        if user and check_password_hash(user["password_hash"], request.form["password"]):
            session.clear()
            session.update(user_id=user["id"], username=user["username"],
                           name=user["full_name"], role=user["role"])
            return redirect(url_for("dashboard"))
        flash("Invalid username or password.", "danger")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/dashboard")
@login_required()
def dashboard():
    if session["role"] == "admin":
        return redirect(url_for("admin"))
    leaves = get_db().execute(
        "SELECT * FROM leaves WHERE user_id=? ORDER BY id DESC", (session["user_id"],)).fetchall()
    return render_template("dashboard.html", leaves=leaves)


@app.route("/apply", methods=["GET", "POST"])
@login_required("employee")
def apply():
    if request.method == "POST":
        lt, sd, ed = request.form["leave_type"], request.form["start_date"], request.form["end_date"]
        reason = request.form["reason"].strip()
        if ed < sd:
            flash("End date cannot be before start date.", "danger")
        else:
            db = get_db()
            db.execute("""INSERT INTO leaves(user_id,leave_type,start_date,end_date,reason,applied_on)
                          VALUES(?,?,?,?,?,?)""",
                       (session["user_id"], lt, sd, ed, reason, date.today().isoformat()))
            db.commit()
            flash("Leave request submitted.", "success")
            return redirect(url_for("dashboard"))
    return render_template("apply.html", today=date.today().isoformat())


@app.route("/admin")
@login_required("admin")
def admin():
    leaves = get_db().execute("""SELECT l.*, u.full_name FROM leaves l
                                 JOIN users u ON u.id=l.user_id
                                 ORDER BY (l.status='Pending') DESC, l.id DESC""").fetchall()
    return render_template("admin.html", leaves=leaves)


@app.route("/decide/<int:leave_id>/<action>", methods=["POST"])
@login_required("admin")
def decide(leave_id, action):
    if action not in ("approve", "reject"):
        return redirect(url_for("admin"))
    status = "Approved" if action == "approve" else "Rejected"
    db = get_db()
    db.execute("UPDATE leaves SET status=?, decided_by=? WHERE id=? AND status='Pending'",
               (status, session["username"], leave_id))
    db.commit()
    flash(f"Request #{leave_id} {status.lower()}.", "success")
    return redirect(url_for("admin"))


init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
