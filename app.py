
import os
import sqlite3
from pathlib import Path
from functools import wraps
from contextlib import contextmanager

from flask import (
    Flask, render_template, request,
    redirect, url_for, session, flash
)
from werkzeug.security import generate_password_hash, check_password_hash


# ==========================================
# FLASK CONFIGURATION
# ==========================================

app = Flask(__name__)

app.secret_key = os.environ.get(
    "SECRET_KEY",
    "personaforge-development-key-change-before-deployment"
)

DATABASE = Path(app.root_path) / "personaforge.db"


# ==========================================
# DATABASE CONNECTION
# ==========================================

@contextmanager
def get_db():
    db = sqlite3.connect(DATABASE, timeout=10)
    db.row_factory = sqlite3.Row

    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def init_db():
    with get_db() as db:

        # Existing user accounts
        db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL
            )
        """)

        # Permanent interview answers
        db.execute("""
            CREATE TABLE IF NOT EXISTS interview_answers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                question TEXT NOT NULL,
                answer TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, question),
                FOREIGN KEY(user_id) REFERENCES users(id)
                    ON DELETE CASCADE
            )
        """)

        # Permanent BrandMind selection
        db.execute("""
            CREATE TABLE IF NOT EXISTS brand_preferences (
                user_id INTEGER PRIMARY KEY,
                selected_brand TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(id)
                    ON DELETE CASCADE
            )
        """)


init_db()


# ==========================================
# DATABASE HELPERS
# ==========================================

def get_user_answers(user_id):
    with get_db() as db:
        rows = db.execute("""
            SELECT question, answer
            FROM interview_answers
            WHERE user_id = ?
            ORDER BY id ASC
        """, (user_id,)).fetchall()

    return [dict(row) for row in rows]


def save_answer(user_id, question, answer):
    with get_db() as db:
        db.execute("""
            INSERT INTO interview_answers
                (user_id, question, answer)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id, question)
            DO UPDATE SET
                answer = excluded.answer,
                updated_at = CURRENT_TIMESTAMP
        """, (user_id, question, answer))


def get_selected_brand(user_id):
    with get_db() as db:
        row = db.execute("""
            SELECT selected_brand
            FROM brand_preferences
            WHERE user_id = ?
        """, (user_id,)).fetchone()

    return row["selected_brand"] if row else ""


def save_selected_brand(user_id, brand):
    with get_db() as db:
        db.execute("""
            INSERT INTO brand_preferences (user_id, selected_brand)
            VALUES (?, ?)
            ON CONFLICT(user_id)
            DO UPDATE SET
                selected_brand = excluded.selected_brand,
                updated_at = CURRENT_TIMESTAMP
        """, (user_id, brand))


# ==========================================
# LOGIN PROTECTION
# ==========================================

def login_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if not session.get("user_id"):
            flash("Please log in to continue.", "error")
            return redirect(url_for("login"))
        return view(*args, **kwargs)

    return wrapped_view


# ==========================================
# HOME
# ==========================================

@app.route("/")
def index():
    return render_template("index.html")


# ==========================================
# REGISTER
# ==========================================

@app.route("/register", methods=["GET", "POST"])
def register():
    if session.get("user_id"):
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not email or not password or not confirm_password:
            return render_template(
                "register.html",
                error="Please fill in all fields."
            )

        if len(password) < 8:
            return render_template(
                "register.html",
                error="Password must contain at least 8 characters."
            )

        if password != confirm_password:
            return render_template(
                "register.html",
                error="Passwords do not match."
            )

        try:
            with get_db() as db:
                cursor = db.execute("""
                    INSERT INTO users (email, password_hash)
                    VALUES (?, ?)
                """, (email, generate_password_hash(password)))

                user_id = cursor.lastrowid

            session.clear()
            session["user_id"] = user_id
            session["user_email"] = email

            return redirect(url_for("dashboard"))

        except sqlite3.IntegrityError:
            return render_template(
                "register.html",
                error="This email is already registered. Please log in."
            )

        except sqlite3.Error:
            app.logger.exception("Registration database error")
            return render_template(
                "register.html",
                error="Unable to create your account. Please try again."
            )

    return render_template("register.html")


# ==========================================
# LOGIN
# ==========================================

@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("user_id"):
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if not email or not password:
            return render_template(
                "login.html",
                error="Please enter your email and password."
            )

        try:
            with get_db() as db:
                user = db.execute("""
                    SELECT id, email, password_hash
                    FROM users
                    WHERE email = ?
                """, (email,)).fetchone()

        except sqlite3.Error:
            app.logger.exception("Login database error")
            return render_template(
                "login.html",
                error="Unable to access your account. Please try again."
            )

        if user and check_password_hash(
            user["password_hash"], password
        ):
            session.clear()
            session["user_id"] = user["id"]
            session["user_email"] = user["email"]

            return redirect(url_for("dashboard"))

        return render_template(
            "login.html",
            error="Invalid email or password. Please try again."
        )

    return render_template("login.html")


# ==========================================
# FORGOT PASSWORD
# ==========================================

@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()

        if not email:
            return render_template(
                "forgot_password.html",
                error="Please enter your registered email address."
            )

        # Actual password-reset email is not configured yet.
        flash(
            "Password reset email is not configured yet. "
            "Please contact the administrator.",
            "info"
        )
        return redirect(url_for("forgot_password"))

    return render_template("forgot_password.html")


# ==========================================
# LOGOUT
# ==========================================

@app.route("/logout", methods=["GET", "POST"])
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("login"))


# ==========================================
# DASHBOARD
# ==========================================

@app.route("/dashboard")
@login_required
def dashboard():
    return render_template("dashboard.html")


# ==========================================
# INTERVIEW QUESTIONS
# ==========================================

INTERVIEW_QUESTIONS = [
    {
        "label": "LET'S START WITH THE BASICS",
        "title": "Tell us about yourself.",
        "description": (
            "Introduce yourself and tell us what you are "
            "currently studying or working on."
        )
    },
    {
        "label": "YOUR EDUCATION",
        "title": "Tell us about your education.",
        "description": "Tell us about your degree, college and area of study."
    },
    {
        "label": "YOUR SKILLS",
        "title": "What are your main skills?",
        "description": "Tell us about your technical and professional skills."
    },
    {
        "label": "YOUR PROJECTS",
        "title": "Tell us about your projects.",
        "description": "Describe projects you have built and the technologies you used."
    },
    {
        "label": "YOUR EXPERIENCE",
        "title": "Tell us about your experience.",
        "description": "Tell us about internships, jobs or other relevant experience."
    },
    {
        "label": "YOUR GOALS",
        "title": "What are your career goals?",
        "description": "Tell us about your future career goals."
    }
]


# ==========================================
# AI INTERVIEW
# ==========================================

@app.route("/interview", methods=["GET", "POST"])
@login_required
def interview():
    user_id = session["user_id"]
    total = len(INTERVIEW_QUESTIONS)

    try:
        current = int(session.get("interview_step", 1))
    except (TypeError, ValueError):
        current = 1

    current = max(1, min(current, total))

    if request.method == "POST":
        answer = request.form.get("answer", "").strip()

        if not answer:
            flash("Please enter your answer before continuing.", "error")
            return redirect(url_for("interview"))

        question_title = INTERVIEW_QUESTIONS[current - 1]["title"]

        try:
            save_answer(user_id, question_title, answer[:1000])
        except sqlite3.Error:
            app.logger.exception("Unable to save interview answer")
            flash("Could not save your answer. Please try again.", "error")
            return redirect(url_for("interview"))

        if current == total:
            session["interview_step"] = 1
            return redirect(url_for("interview_complete"))

        session["interview_step"] = current + 1
        return redirect(url_for("interview"))

    question = INTERVIEW_QUESTIONS[current - 1]

    # Show the saved answer if the user returns to a question.
    answers = get_user_answers(user_id)
    saved_answer = next(
        (
            item["answer"] for item in answers
            if item["question"] == question["title"]
        ),
        ""
    )

    return render_template(
        "interview.html",
        question=question,
        current=current,
        total=total,
        percentage=round(current / total * 100),
        saved_answer=saved_answer
    )


# ==========================================
# INTERVIEW COMPLETE
# ==========================================

@app.route("/interview-complete")
@login_required
def interview_complete():
    user_id = session["user_id"]
    interview_answers = get_user_answers(user_id)

    return render_template(
        "interview_complete.html",
        interview_answers=interview_answers
    )




@app.route("/profile")
@login_required
def profile():
    user_id = session["user_id"]

    interview_answers = get_user_answers(user_id)

    with get_db() as db:
        user = db.execute(
            "SELECT email FROM users WHERE id = ?",
            (user_id,)
        ).fetchone()

    user_email = user["email"] if user else "Your Account"

    return render_template(
        "profile.html",
        interview_answers=interview_answers,
        user_email=user_email
    )



# ==========================================
# AI GENERATOR PAGE
# ==========================================

@app.route("/generator")
@login_required
def generator():
    return render_template(
        "generator.html",
        generated_content=None,
        generator_type=None
    )


# ==========================================
# GENERATE PROFESSIONAL CONTENT
# ==========================================

@app.route("/generate/<content_type>")
@login_required
def generate_content(content_type):
    allowed_types = {"resume", "linkedin", "github", "bio"}

    if content_type not in allowed_types:
        return "Invalid content type", 404

    answers = get_user_answers(session["user_id"])

    if not answers:
        return render_template(
            "generator.html",
            generated_content=None,
            generator_type=content_type,
            message=(
                "Complete your AI Interview first to generate "
                "personalized content."
            )
        )

    profile_data = {}

    for item in answers:
        question = item["question"].lower()
        answer = item["answer"].strip()

        if "yourself" in question or "about you" in question:
            profile_data["about"] = answer
        elif "education" in question:
            profile_data["education"] = answer
        elif "skills" in question:
            profile_data["skills"] = answer
        elif "project" in question:
            profile_data["projects"] = answer
        elif "experience" in question:
            profile_data["experience"] = answer
        elif "goal" in question or "career" in question:
            profile_data["goals"] = answer

    about = profile_data.get("about", "Not provided")
    education = profile_data.get("education", "Not provided")
    skills = profile_data.get("skills", "Not provided")
    projects = profile_data.get("projects", "Not provided")
    experience = profile_data.get("experience", "Not provided")
    goals = profile_data.get("goals", "Not provided")

    if content_type == "resume":
        heading = "Your Professional Resume"
        sections = [
            ("PROFESSIONAL SUMMARY", about),
            ("EDUCATION", education),
            ("SKILLS", skills),
            ("PROJECTS", projects),
            ("EXPERIENCE", experience),
            ("CAREER OBJECTIVE", goals)
        ]

    elif content_type == "linkedin":
        heading = "Your LinkedIn About"
        sections = [
            (
                "ABOUT",
                f"I am a motivated individual with this background: {about}"
            ),
            ("EDUCATION", education),
            ("SKILLS", skills),
            ("PROJECTS AND EXPERIENCE", f"{projects}\n\n{experience}"),
            ("CAREER INTERESTS", goals)
        ]

    elif content_type == "github":
        heading = "Your GitHub Profile README"
        sections = [
            ("INTRODUCTION", about),
            ("EDUCATION", education),
            ("TECHNICAL SKILLS", skills),
            ("PROJECTS", projects),
            ("EXPERIENCE", experience),
            ("CURRENT GOALS", goals)
        ]

    else:
        heading = "Your Professional Biography"
        sections = [
            (
                "BIOGRAPHY",
                f"{about}\n\nEducation: {education}\n\n"
                f"Skills: {skills}\n\nProjects: {projects}\n\n"
                f"Experience: {experience}\n\nCareer goals: {goals}"
            )
        ]

    generated_content = {
        "heading": heading,
        "sections": sections
    }

    return render_template(
        "generator.html",
        generated_content=generated_content,
        generator_type=content_type
    )


# ==========================================
# BRANDMIND AI
# ==========================================

@app.route("/brandmind", methods=["GET", "POST"])
@login_required
def brandmind():
    user_id = session["user_id"]

    allowed_brands = [
        "Professional",
        "Creative",
        "Premium",
        "Futuristic",
        "Technical"
    ]

    if request.method == "POST":
        selected_brand = request.form.get(
            "brand_persona", ""
        ).strip()

        if selected_brand not in allowed_brands:
            flash("Please select a valid brand style.", "error")
            return redirect(url_for("brandmind"))

        try:
            save_selected_brand(user_id, selected_brand)
            flash("Branding preference saved!", "success")
        except sqlite3.Error:
            app.logger.exception("Unable to save brand preference")
            flash("Unable to save your selection. Please try again.", "error")

        return redirect(url_for("brandmind"))

    return render_template(
        "brandmind.html",
        selected_brand=get_selected_brand(user_id)
    )


# ==========================================
# PORTFOLIO
# ==========================================

@app.route("/portfolio")
@login_required
def portfolio():
    user_id = session["user_id"]

    return render_template(
        "portfolio.html",
        selected_brand=get_selected_brand(user_id),
        interview_answers=get_user_answers(user_id)
    )


# ==========================================
# SETTINGS
# ==========================================

@app.route("/settings")
@login_required
def settings():
    return render_template("settings.html")


# ==========================================
# RESET INTERVIEW
# ==========================================

@app.route("/reset-interview", methods=["POST"])
@login_required
def reset_interview():
    user_id = session["user_id"]

    try:
        with get_db() as db:
            db.execute(
                "DELETE FROM interview_answers WHERE user_id = ?",
                (user_id,)
            )

        session["interview_step"] = 1
        flash("Your interview answers have been reset.", "success")

    except sqlite3.Error:
        app.logger.exception("Unable to reset interview answers")
        flash("Could not reset your answers. Please try again.", "error")

    return redirect(url_for("interview"))


# ==========================================
# ERROR HANDLERS
# ==========================================

@app.errorhandler(404)
def page_not_found(error):
    return "Page not found. Please check the URL.", 404


@app.errorhandler(500)
def internal_server_error(error):
    app.logger.exception("Internal server error: %s", error)
    return (
        "<h1>Server error</h1>"
        "<p>Something went wrong. Check the Flask terminal for details.</p>",
        500
    )


# ==========================================
# RUN APP
# ==========================================

if __name__ == "__main__":
    app.run(debug=True)
