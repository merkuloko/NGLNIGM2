import hmac
import os
import secrets
import time

from flask import Flask, abort, jsonify, redirect, render_template, request, session, url_for
from supabase import create_client


API_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(API_DIR)
TEMPLATE_DIR = os.path.join(API_DIR, "templates")
STATIC_DIR = os.path.join(API_DIR, "static")

if not os.path.isdir(TEMPLATE_DIR):
    TEMPLATE_DIR = os.path.join(BASE_DIR, "templates")

if not os.path.isdir(STATIC_DIR):
    STATIC_DIR = os.path.join(BASE_DIR, "static")

MESSAGE_MAX_LENGTH = 1000
LOGIN_WINDOW_SECONDS = 300
MAX_LOGIN_ATTEMPTS = 5


app = Flask(
    __name__,
    template_folder=TEMPLATE_DIR,
    static_folder=STATIC_DIR,
)

SECRET_KEY = os.environ.get("SECRET_KEY")
IS_PRODUCTION = os.environ.get("VERCEL_ENV") == "production"

if not SECRET_KEY:
    if IS_PRODUCTION:
        raise RuntimeError("SECRET_KEY is required in production")
    SECRET_KEY = secrets.token_urlsafe(32)
    print(
        "WARNING: SECRET_KEY is not set. Using a generated development key; "
        "sessions will reset when the process restarts."
    )

app.config.update(
    SECRET_KEY=SECRET_KEY,
    MAX_CONTENT_LENGTH=16 * 1024,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=IS_PRODUCTION,
)

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD") or SECRET_KEY

supabase = None
if SUPABASE_URL and SUPABASE_KEY:
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception:
        app.logger.exception("Supabase initialization failed")
else:
    app.logger.warning("Supabase environment variables are missing")


def get_csrf_token():
    token = session.get("_csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["_csrf_token"] = token
    return token


app.jinja_env.globals["csrf_token"] = get_csrf_token


def validate_csrf():
    form_token = request.form.get("csrf_token", "")
    session_token = session.get("_csrf_token", "")
    if not form_token or not session_token or not hmac.compare_digest(form_token, session_token):
        abort(400, description="Invalid CSRF token")


def get_login_state():
    now = int(time.time())
    state = session.get("login_rate_limit", {"count": 0, "first_attempt": now})
    elapsed = now - state.get("first_attempt", now)
    if elapsed > LOGIN_WINDOW_SECONDS:
        state = {"count": 0, "first_attempt": now}
    return state


def record_failed_login():
    state = get_login_state()
    state["count"] += 1
    session["login_rate_limit"] = state


def clear_failed_logins():
    session.pop("login_rate_limit", None)


def is_login_blocked():
    state = get_login_state()
    return state["count"] >= MAX_LOGIN_ATTEMPTS


@app.errorhandler(400)
def handle_bad_request(error):
    if request.path == "/send":
        return jsonify({"status": "error", "message": "Invalid request."}), 400
    return render_template("login.html", error=error.description), 400


@app.errorhandler(413)
def handle_large_payload(_error):
    return jsonify({"status": "error", "message": "Haba masyado. Paki Iklian Please. Send kanalang ulit pagka tapos nito"}), 413


@app.route("/")
def home():
    return render_template("index.html", message_max_length=MESSAGE_MAX_LENGTH)


@app.route("/send", methods=["POST"])
def send_message():
    validate_csrf()

    if supabase is None:
        app.logger.error("Message submission attempted without database configuration")
        return jsonify({"status": "error", "message": "Service is unavailable right now."}), 503

    message_content = (request.form.get("message") or "").strip()
    if not message_content:
        return jsonify({"status": "error", "message": "Oh? Ba't walang laman? 'di to mas-send kung walang laman."}), 400

    if len(message_content) > MESSAGE_MAX_LENGTH:
        return jsonify(
            {
                "status": "error",
                "message": f"Message must be {MESSAGE_MAX_LENGTH} characters or fewer. Send kanalang uli pagka tapos nito.",
            }
        ), 400

    try:
        supabase.table("anonymous_messages").insert({"content": message_content}).execute()
        return jsonify({"status": "success"}), 200
    except Exception:
        app.logger.exception("Failed to store anonymous message")
        return jsonify({"status": "error", "message": "Could not send message right now."}), 500


@app.route("/view-messages-99", methods=["GET"])
def view_messages():
    if not session.get("admin_logged_in"):
        error = None
        if is_login_blocked():
            error = "Too many failed attempts. Wait ka few minutes tapos try mo ulit."
        return render_template("login.html", error=error)

    if supabase is None:
        app.logger.error("Admin view attempted without database configuration")
        return render_template("admin.html", messages=[], error="Database is not configured.")

    try:
        response = (
            supabase.table("anonymous_messages")
            .select("*")
            .order("created_at", desc=True)
            .execute()
        )
        return render_template("admin.html", messages=response.data or [], error=None)
    except Exception:
        app.logger.exception("Failed to load anonymous messages")
        return render_template("admin.html", messages=[], error="Could not load messages right now."), 500


@app.route("/admin-login", methods=["POST"])
def admin_login():
    validate_csrf()

    if not ADMIN_PASSWORD:
        app.logger.error("Admin login attempted without ADMIN_PASSWORD or SECRET_KEY configured")
        return render_template(
            "login.html",
            error="Admin access is not configured. Set ADMIN_PASSWORD in Vercel.",
        ), 503

    if is_login_blocked():
        return render_template(
            "login.html",
            error="Too many failed attempts. Please wait a few minutes and try again.",
        ), 429

    password = request.form.get("password", "")
    if hmac.compare_digest(password, ADMIN_PASSWORD):
        session.clear()
        session["_csrf_token"] = secrets.token_urlsafe(32)
        session["admin_logged_in"] = True
        clear_failed_logins()
        return redirect(url_for("view_messages"))

    record_failed_login()
    return render_template("login.html", error="Incorrect password."), 401


@app.route("/admin-logout", methods=["POST"])
def admin_logout():
    validate_csrf()
    session.clear()
    session["_csrf_token"] = secrets.token_urlsafe(32)
    return redirect(url_for("view_messages"))


if __name__ == "__main__":
    app.run()
