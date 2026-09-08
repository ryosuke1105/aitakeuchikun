import os
import threading
from flask import Flask, render_template, request, jsonify, session
from dotenv import load_dotenv
from drive_loader import DriveGeminiService

# Load environment variables from .env if present
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "cyber_kawaii_default_secret_key_2026")

# Environment variables
APP_PASSWORD = os.getenv("APP_PASSWORD", "CYBER_SECRET_2026")

# Initialize Drive & Gemini Service instance
drive_service = DriveGeminiService()

# Background Pre-fetch on Server Startup so first question is instant
def _warmup_drive_cache():
    try:
        print("[Startup Pre-fetch] Background loading Google Drive PDFs...")
        drive_service.fetch_all_pdfs(force_refresh=True)
        print("[Startup Pre-fetch] Google Drive PDF cache warm-up COMPLETE!")
    except Exception as e:
        print(f"[Startup Pre-fetch] Info: {e}")

threading.Thread(target=_warmup_drive_cache, daemon=True).start()


@app.route('/')
def index():
    """Render the main SPA index page."""
    is_authenticated = session.get('authenticated', False)
    return render_template('index.html', authenticated=is_authenticated)

@app.route('/api/login', methods=['POST'])
def login():
    """Authenticate user with APP_PASSWORD."""
    data = request.get_json() or {}
    password = data.get('password', '')

    if password == APP_PASSWORD:
        session['authenticated'] = True
        return jsonify({
            "success": True,
            "message": "AUTHENTICATION SUCCESSFUL. ACCESS GRANTED."
        })
    else:
        return jsonify({
            "success": False,
            "message": "ACCESS DENIED: INVALID SECURITY PASSWORD."
        }), 401

@app.route('/api/logout', methods=['POST'])
def logout():
    """Clear session and log out."""
    session.clear()
    return jsonify({
        "success": True,
        "message": "LOGGED OUT."
    })

@app.route('/api/session', methods=['GET'])
def get_session():
    """Return session state."""
    return jsonify({
        "authenticated": session.get('authenticated', False)
    })

@app.route('/api/ask', methods=['POST'])
def ask_question():
    """Q&A endpoint (Requires authentication session)."""
    if not session.get('authenticated'):
        return jsonify({
            "error": "UNAUTHORIZED: Access restricted. Please authenticate first."
        }), 401

    data = request.get_json() or {}
    question = data.get('question', '').strip()
    max_chars = data.get('max_chars', 300)

    if not question:
        return jsonify({
            "error": "質問内容を入力してください。"
        }), 400

    try:
        max_chars = int(max_chars)
        max_chars = max(10, min(max_chars, 2000))
    except (ValueError, TypeError):
        max_chars = 300

    # Process query through Google Drive PDF Context + Gemini API
    result = drive_service.ask_gemini(question=question, max_chars=max_chars)
    return jsonify(result)

@app.route('/api/drive/status', methods=['GET'])
def drive_status():
    """Check target Google Drive PDFs status."""
    if not session.get('authenticated'):
        return jsonify({"error": "UNAUTHORIZED"}), 401

    pdfs = drive_service.fetch_all_pdfs()
    return jsonify({
        "count": len(pdfs),
        "files": [pdf["name"] for pdf in pdfs],
        "has_credentials": bool(os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")),
        "has_folder_id": bool(os.getenv("GOOGLE_DRIVE_FOLDER_ID")),
        "has_gemini_key": bool(os.getenv("GEMINI_API_KEY"))
    })

if __name__ == '__main__':
    port = int(os.getenv("PORT", 5000))
    print(f"[+] Cyber Kawaii Server starting on http://localhost:{port}")
    app.run(host='0.0.0.0', port=port, debug=False)



