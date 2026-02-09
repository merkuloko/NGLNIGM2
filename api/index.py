import os
from flask import Flask, render_template, request, jsonify, session, redirect
from supabase import create_client, Client

app = Flask(__name__, template_folder="../templates", static_folder="../static")
app.secret_key = os.environ.get("SECRET_KEY", "change-this-secret")

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

supabase = None
if SUPABASE_URL and SUPABASE_KEY:
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception as e:
        print("Supabase init failed:", e)

@app.route("/")
def home():
    return render_template("index.html")


@app.route("/send", methods=["POST"])
def send_message():
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

    try:
        response = supabase.table("anonymous_messages") \
            .select("*") \
            .order("timestamp", desc=True) \
            .execute()

        return render_template("admin.html", messages=response.data)

    except Exception as e:
        return f"Error: {e}"


@app.route("/admin-login", methods=["POST"])
def admin_login():
    if request.form.get("password") == "open-sesame":
        session["admin_logged_in"] = True
        return redirect("/view-messages-99")

    return "Wrong password. <a href='/view-messages-99'>Try again</a>"
