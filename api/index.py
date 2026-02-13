import os
from flask import Flask, render_template, request, jsonify, session, redirect
from supabase import create_client, Client

# --- Flask setup ---
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "pogi_si_gm_12345")

# --- Supabase setup ---
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

supabase = None
if SUPABASE_URL and SUPABASE_KEY:
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        print("Supabase initialized successfully")
    except Exception as e:
        print("Supabase init failed:", e)
else:
    print("Supabase env vars missing!")

# --- Home page ---
@app.route("/")
def home():
    return render_template("index.html")

# --- Send anonymous message ---
@app.route("/send", methods=["POST"])
def send_message():
    if supabase is None:
        return jsonify({"status": "error", "message": "Database not configured"}), 500

    message_content = request.form.get("message")
    if not message_content:
        return jsonify({"status": "error", "message": "Message is empty"}), 400

    try:
        supabase.table("anonymous_messages").insert({
            "content": message_content
        }).execute()
        return jsonify({"status": "success"}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# --- View messages (admin only) ---
@app.route("/view-messages-99")
def view_messages():
    if not session.get("admin_logged_in"):
        return """
        <div style="text-align:center;margin-top:50px;font-family:sans-serif;">
            <form action="/admin-login" method="post">
                <input type="password" name="password" placeholder="Password?">
                <button type="submit">Enter</button>
            </form>
        </div>
        """

    if supabase is None:
        return "Database not configured"

    try:
        response = (
            supabase.table("anonymous_messages")
            .select("*")
            .order("created_at", desc=True)
            .execute()
        )

        return render_template("admin.html", messages=response.data)

    except Exception as e:
        return f"Error: {e}"


# --- Admin login ---
@app.route("/admin-login", methods=["POST"])
def admin_login():
    if request.form.get("password") == "open-sesame":
        session["admin_logged_in"] = True
        return redirect("/view-messages-99")
    return "Mali password mo, em. <a href='/view-messages-99'>Try again</a>"

# --- Debug prints ---
print("Supabase URL:", SUPABASE_URL)
print("Supabase key exists:", bool(SUPABASE_KEY))

app = app

if __name__ == "__main__":
    app.run()
