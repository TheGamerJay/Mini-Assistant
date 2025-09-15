# Mini Assistant — "My Homework Buddy" + Life Skills + Forms
# CPU-friendly, single-file Flask app with:
# - Text & Photo (vision) homework help
# - Kid / Parent / Step-by-Step modes
# - Guided Coach sessions (one-step-at-a-time, hints, reveal)
# - Always ends with "Why this answer is correct" + "Check Your Work"
# - Printable worksheet PDF generator
# - Generic fillable PDF form filler & flattener
# - Daily free IP limit + optional Stripe Payment Link
#
# ENV (Railway):
#   OPENAI_API_KEY=sk-...
#   OPENAI_MODEL=gpt-4o-mini          (default)
#   FREE_DAILY_LIMIT=5                (optional)
#   STRIPE_PAY_LINK=https://buy...    (optional)
#   SECRET_KEY=change-this            (for sessions)
#
# Run local:
#   pip install -r requirements.txt
#   python app.py

import os, io, json, base64, re, sqlite3, datetime, ipaddress
import requests
from flask import Flask, request, render_template_string, redirect, url_for, abort, send_file, send_from_directory
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.units import inch
from reportlab.lib.utils import simpleSplit
from pypdf import PdfReader, PdfWriter

APP_NAME = "Mini Assistant"
API_KEY = os.getenv("OPENAI_API_KEY", "")
MODEL   = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
FREE_DAILY_LIMIT = int(os.getenv("FREE_DAILY_LIMIT", "5"))
STRIPE_PAY_LINK  = os.getenv("STRIPE_PAY_LINK", "")
SECRET_KEY = os.getenv("SECRET_KEY", "dev-mini-assistant-change-me")
DB_PATH = os.getenv("DB_PATH", "mini_assistant.sqlite")

if not API_KEY:
    raise SystemExit("Missing OPENAI_API_KEY")

app = Flask(__name__)
app.secret_key = SECRET_KEY
app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024  # 25MB

# ---------- usage DB (IP/day limit) ----------
def init_db():
    with sqlite3.connect(DB_PATH) as con:
        con.execute("""
        CREATE TABLE IF NOT EXISTS usage (
            ip TEXT NOT NULL,
            day TEXT NOT NULL,
            count INTEGER NOT NULL,
            PRIMARY KEY (ip, day)
        )""")
init_db()

def client_ip():
    fwd = request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
    ip = fwd or (request.remote_addr or "0.0.0.0")
    try: ipaddress.ip_address(ip)
    except: ip = "0.0.0.0"
    return ip

def can_use_free():
    if FREE_DAILY_LIMIT <= 0: return True
    ip, today = client_ip(), datetime.date.today().isoformat()
    with sqlite3.connect(DB_PATH) as con:
        row = con.execute("SELECT count FROM usage WHERE ip=? AND day=?", (ip, today)).fetchone()
        used = row[0] if row else 0
        return used < FREE_DAILY_LIMIT

def bump_usage():
    if FREE_DAILY_LIMIT <= 0: return
    ip, today = client_ip(), datetime.date.today().isoformat()
    with sqlite3.connect(DB_PATH) as con:
        row = con.execute("SELECT count FROM usage WHERE ip=? AND day=?", (ip, today)).fetchone()
        if row:
            con.execute("UPDATE usage SET count=? WHERE ip=? AND day=?", (row[0]+1, ip, today))
        else:
            con.execute("INSERT INTO usage(ip, day, count) VALUES (?, ?, 1)", (ip, today))

# ---------- subject guides ----------
SUBJECT_GUIDES = {
    # Math
    "Arithmetic / Pre-Algebra": "You are a patient math tutor. Focus on integers, fractions, ratios, and simple equations.",
    "Algebra I": "You are an Algebra I tutor. Focus on linear equations, inequalities, graphing, factoring basics.",
    "Algebra II": "You are an Algebra II tutor. Focus on quadratics, polynomials, rational expressions, logs/exponentials.",
    "Geometry": "You are a Geometry tutor. Focus on theorems, proofs, angles, triangles, circles. Describe diagrams in words.",
    "Trigonometry": "You are a Trigonometry tutor. Focus on trig ratios, identities, unit circle, angles.",
    "Pre-Calculus": "You are a Pre-Calculus tutor. Focus on functions, complex numbers, sequences, intro limits.",
    "Calculus": "You are a Calculus tutor. Focus on limits, derivatives, integrals, applications.",
    "Statistics": "You are a Statistics tutor. Focus on descriptive stats, probability, sampling, significance basics.",
    # Science
    "Biology": "You are a Biology tutor. Explain processes (cell division, genetics, photosynthesis) with simple analogies.",
    "Chemistry": "You are a Chemistry tutor. Focus on reactions, stoichiometry, bonding, periodic trends; balance equations.",
    "Physics": "You are a Physics tutor. Identify knowns/unknowns, apply formulas, check physical sense.",
    "Earth Science": "You are an Earth Science tutor. Cover geology, weather, oceans, ecosystems with simple steps.",
    # English/Lang Arts
    "English / Grammar": "You are a Language Arts tutor. Help with grammar, punctuation, sentence clarity, examples.",
    "Literature Analysis": "You analyze texts (theme, tone, evidence). Use quotes sparingly; explain relevance.",
    "Essay Writing": "You teach structure: thesis, topic sentences, evidence, transitions, conclusion.",
    # History/Soc Studies
    "World History": "You provide context (who/what/when/why), causes/effects, significance; dates precise.",
    "U.S. History": "You explain events, constitutional principles, timelines, and their significance clearly.",
    "Civics / Government": "You explain branches, rights, responsibilities, processes (elections, laws).",
    "Geography": "You explain regions, climate, human-environment interaction; map reasoning in words.",
    # Tech
    "Computer Science": "You are a CS tutor. Explain algorithms, logic, simple code; use pseudocode if helpful.",
    # Life Skills — Finance & Insurance, Adulting, Health, Civic
    "Life — Writing a Check": "Teach how to write a check: date, payee, numeric/written amount, memo, signature; anti-fraud tips.",
    "Life — Budgeting": "Teach tracking expenses, simple budget creation, categories, monthly checkup.",
    "Life — Credit & Interest": "Explain APR, minimum payments, compounding; show small examples; warn pitfalls.",
    "Life — Taxes & Pay Stubs": "Explain gross vs net, withholdings, deductions, W-2 vs 1099 basics.",
    "Life — Insurance Basics": "Explain premiums, deductibles, copays, out-of-pocket max, coverage vs exclusions.",
    "Life — Insurance Claims": "Show step-by-step: document, contact, claim number, follow-up, timelines.",
    "Life — Résumé Writing": "Teach structure: header, summary, experience (bullets w/ impact), skills, education.",
    "Life — Professional Email": "Teach subject, greeting, body clarity, closing, signature; provide a sample.",
    "Life — Reading a Lease": "Explain terms: rent, deposit, utilities, notice, fees, maintenance, move-out duties.",
    "Life — Nutrition Labels": "Explain serving size, calories, macros, %DV; quick health comparisons.",
    "Civic — Voter Registration": "Explain how to check eligibility, register, deadlines, and what to bring.",
}

MODE_GUIDES = {
    "Kid": "Rewrite for a student. Friendly, simple words, small steps, one quick example.",
    "Parent": "Fast refresher for a parent. Compare classic vs current method if relevant. 30s summary + 3 talking points.",
    "Step-by-Step": """Show all steps clearly and explain why each step is valid.
Finish with two mini sections:
- Why this answer is correct (2–4 sentences)
- Check Your Work (a quick verification)"""
}

COACH_RULES = """COACH MODE (very important):
- Do NOT just give the final answer. Proceed one step at a time and ask ONE short question after each major step.
- When explicitly asked to reveal the final answer, show the worked solution briefly and ALWAYS include:
  1) Why this answer is correct (2–4 sentences)
  2) Check Your Work (a quick verification)
- Be friendly, concise, and focus on learning, not just results.
"""

POLICY_REMINDER = """Important rules:
- Help the student learn; avoid enabling cheating. Provide guidance and explanations.
- If the question looks like a live test/quiz, focus on method and learning steps instead of final answers.
- Always end solutions with 'Why this answer is correct' and 'Check Your Work' where appropriate.
"""

# ---------- OpenAI helpers ----------
def call_openai_chat(messages, temperature=0.3):
    url = "https://api.openai.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {API_KEY}"}
    data = {"model": MODEL, "temperature": temperature, "messages": messages}
    r = requests.post(url, json=data, headers=headers, timeout=120)
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]

def build_text_messages(subject, mode, question, coach_mode=False):
    sys = f"""You are Mini Assistant, a friendly tutor.
Subject: {subject}.
{SUBJECT_GUIDES.get(subject,'')}
Mode: {mode}.
{MODE_GUIDES.get(mode,'')}
{POLICY_REMINDER}
{COACH_RULES if coach_mode else ''}"""
    user = f"""
Homework or life-skill question:
{(question or '').strip()}

Respond in Markdown with clear headings and bullets.
Always end with:
- Why this answer is correct (2–4 sentences)
- Check Your Work (a quick verification)
"""
    return [{"role": "system", "content": sys}, {"role": "user", "content": user}]

def build_vision_messages(subject, mode, image_bytes, filename, extra_text, coach_mode=False):
    mime = "image/png" if filename.lower().endswith(".png") else "image/jpeg"
    b64 = base64.b64encode(image_bytes).decode("utf-8")
    data_url = f"data:{mime};base64,{b64}"

    sys = f"""You are Mini Assistant, a friendly tutor who can read problems from photos.
Extract the question(s) from the image, then teach the method.
Subject: {subject}.
{SUBJECT_GUIDES.get(subject,'')}
Mode: {mode}.
{MODE_GUIDES.get(mode,'')}
{POLICY_REMINDER}
{COACH_RULES if coach_mode else ''}"""
    user_content = [
        {"type": "text", "text": "Read the homework/life-skill problem in this image and coach the student."},
        {"type": "image_url", "image_url": {"url": data_url}},
    ]
    if (extra_text or "").strip():
        user_content.append({"type": "text", "text": f"Extra context from user: {(extra_text or '').strip()}."})
    user_content.append({"type": "text", "text": "Respond in Markdown. Include 'Why this answer is correct' and 'Check Your Work' at the end."})
    return [{"role": "system", "content": sys}, {"role": "user", "content": user_content}]

# ---------- Guided (Socratic) session ----------
SOCRATIC_SYS = """You are Mini Assistant, a strict Socratic homework coach.
Rules:
- Proceed with EXACTLY ONE next step at a time, then ask ONE short question.
- Keep steps small, numbered, clear.
- Give hints when the student is stuck.
- Reveal final answer only on explicit 'Reveal'. When revealing, include:
  (1) Why this answer is correct (2–4 sentences)
  (2) Check Your Work (a quick verification).
- Friendly and concise.
"""

def _pack_history(msgs: list) -> str:
    raw = json.dumps(msgs, ensure_ascii=False)
    return base64.b64encode(raw.encode("utf-8")).decode("ascii")

def _unpack_history(s: str) -> list:
    try:
        raw = base64.b64decode(s.encode("ascii")).decode("utf-8")
        return json.loads(raw)
    except Exception:
        return []

def build_guided_messages(subject, mode, problem_text=None, photo_data_url=None, history=None):
    if history: return history
    sys = SOCRATIC_SYS
    user_content = []
    if (problem_text or "").strip():
        user_content.append({"type":"text","text": f"Here is the student's problem:\n{(problem_text or '').strip()}"} )
    if photo_data_url:
        user_content.append({"type":"image_url","image_url":{"url": photo_data_url}})
        user_content.append({"type":"text","text":"Please read the problem from the image accurately."})
    user_content.append({"type":"text","text":"Start with step 1 only, then ask me one short question."})
    return [
        {"role":"system","content":sys},
        {"role":"user","content":user_content}
    ]

# ---------- PDF: worksheet builder ----------
def _draw_block(c, title, text, x, y, width, leading=14, title_leading=16):
    if title:
        c.setFont("Helvetica-Bold", 12)
        for line in simpleSplit(title, "Helvetica-Bold", 12, width):
            c.drawString(x, y, line); y -= title_leading
    if text:
        c.setFont("Helvetica", 11)
        for line in simpleSplit(text, "Helvetica", 11, width):
            c.drawString(x, y, line); y -= leading
    return y

def build_worksheet_pdf(problem, steps_md, final_answer, why_correct, check_work, student_name=""):
    def md_to_lines(md):
        return "\n".join([l.strip().lstrip("-*").strip() for l in (md or "").splitlines()])
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    W, H = letter
    margin = 0.8*inch
    x = margin; y = H - margin
    width = W - 2*margin
    title = "Mini Assistant – Homework Worksheet"
    if student_name: title += f"  ·  {student_name}"
    c.setTitle(title)
    y = _draw_block(c, title, "", x, y, width); y -= 6
    y = _draw_block(c, "Problem", md_to_lines(problem), x, y, width); y -= 6
    y = _draw_block(c, "Guided Steps", md_to_lines(steps_md), x, y, width); y -= 6
    y = _draw_block(c, "Final Answer", str(final_answer or ""), x, y, width); y -= 6
    y = _draw_block(c, "Why this answer is correct", md_to_lines(why_correct), x, y, width); y -= 6
    _ = _draw_block(c, "Check Your Work", md_to_lines(check_work), x, y, width)
    c.showPage(); c.save(); buf.seek(0); return buf

# ---------- PDF: form filler ----------
def fill_pdf_form(pdf_file_stream, field_values: dict):
    reader = PdfReader(pdf_file_stream)
    writer = PdfWriter()
    writer.append(reader)
    writer.update_page_form_field_values(writer.pages[0:len(reader.pages)], field_values)
    try:
        writer.remove_annotations()
    except Exception:
        pass
    writer._root_object.update({"/NeedAppearances": False})
    out = io.BytesIO()
    writer.write(out); out.seek(0); return out

def list_pdf_fields(pdf_file_stream):
    reader = PdfReader(pdf_file_stream)
    fields = {}
    try:
        raw = reader.get_fields()
        if raw:
            for k, v in raw.items():
                fields[k] = str(v.get('/T', k))
    except Exception:
        pass
    return fields

# ---------- UI ----------
INDEX_HTML = """
<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>{{app_name}} — My Homework & Life Skills Buddy</title>
<link rel="icon" href="/static/favicon/favicon.ico">
<link rel="icon" type="image/png" sizes="32x32" href="/static/favicon/favicon-32x32.png">
<link rel="icon" type="image/png" sizes="192x192" href="/static/favicon/favicon-192x192.png">
<link rel="apple-touch-icon" href="/static/favicon/favicon-512x512.png">
<link rel="manifest" href="/static/manifest.json">
<style>
  :root{--bg:#0b0f14;--card:#101823;--ink:#e8eef7;--muted:#94a3b8;--brd:#1f2b3a;--pri:#22c55e}
  *{box-sizing:border-box} body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.5 system-ui,Segoe UI,Roboto,Inter,Helvetica,Arial}
  header{padding:24px 16px;text-align:center;background:#0f1620;border-bottom:1px solid var(--brd)}
  h1{margin:0 0 6px 0;font-size:24px}
  .fine{opacity:.85;color:var(--muted)}
  main{max-width:980px;margin:22px auto;padding:0 16px}
  .card{background:var(--card);border:1px solid var(--brd);border-radius:14px;padding:16px;margin-bottom:16px}
  label{display:block;margin:8px 0 6px;font-weight:600}
  select,textarea,input[type=file],input[type=text],button{width:100%;padding:12px;border-radius:10px;border:1px solid var(--brd);background:#0a121a;color:var(--ink)}
  textarea{min-height:110px;resize:vertical}
  .row{display:grid;grid-template-columns:1fr 1fr;gap:12px}
  .row3{display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px}
  .actions{display:flex;gap:10px;flex-wrap:wrap;margin-top:8px}
  .pill{border:1px solid var(--brd);padding:6px 10px;border-radius:999px}
  button{background:var(--pri);color:#0b0f14;font-weight:800;cursor:pointer}
  button:disabled{opacity:.5;cursor:not-allowed}
  .warn{color:#ffda7b}
  .answer{white-space:pre-wrap;padding:12px;background:#0b1118;border:1px solid var(--brd);border-radius:12px;margin-top:8px}
  footer{max-width:980px;margin:14px auto 28px;padding:0 16px;font-size:13px;opacity:.8}
  a{color:#9ad1ff}
</style>
</head><body>
<header>
  <div style="display:flex;align-items:center;justify-content:center;gap:12px;margin-bottom:8px">
    <img src="/static/logo/Mini Assistant.png" alt="Mini Assistant" style="width:48px;height:48px;border-radius:8px">
    <h1 style="margin:0">{{app_name}} — My Homework & Life Skills Buddy</h1>
  </div>
  <div class="fine">Type a question or upload a photo. Choose mode. Always ends with "Why this is correct" & "Check Your Work". {{limit_note}}</div>
</header>
<main>

  <div class="card">
    <form method="post" action="{{url_for('ask')}}" enctype="multipart/form-data">
      <div class="row">
        <div>
          <label>Subject / Topic</label>
          <select name="subject">
            <optgroup label="Math">
              <option>Arithmetic / Pre-Algebra</option>
              <option>Algebra I</option>
              <option>Algebra II</option>
              <option>Geometry</option>
              <option>Trigonometry</option>
              <option>Pre-Calculus</option>
              <option>Calculus</option>
              <option>Statistics</option>
            </optgroup>
            <optgroup label="Science">
              <option>Biology</option>
              <option>Chemistry</option>
              <option>Physics</option>
              <option>Earth Science</option>
            </optgroup>
            <optgroup label="English / Language Arts">
              <option>English / Grammar</option>
              <option>Literature Analysis</option>
              <option>Essay Writing</option>
            </optgroup>
            <optgroup label="History / Social Studies">
              <option>World History</option>
              <option>U.S. History</option>
              <option>Civics / Government</option>
              <option>Geography</option>
            </optgroup>
            <optgroup label="Technology">
              <option>Computer Science</option>
            </optgroup>
            <optgroup label="Life Skills — Finance & Insurance">
              <option>Life — Writing a Check</option>
              <option>Life — Budgeting</option>
              <option>Life — Credit & Interest</option>
              <option>Life — Taxes & Pay Stubs</option>
              <option>Life — Insurance Basics</option>
              <option>Life — Insurance Claims</option>
            </optgroup>
            <optgroup label="Life Skills — Adulting & Health">
              <option>Life — Résumé Writing</option>
              <option>Life — Professional Email</option>
              <option>Life — Reading a Lease</option>
              <option>Life — Nutrition Labels</option>
            </optgroup>
            <optgroup label="Civic Basics">
              <option>Civic — Voter Registration</option>
            </optgroup>
          </select>
        </div>
        <div>
          <label>Mode</label>
          <select name="mode">
            <option>Kid</option>
            <option>Parent</option>
            <option>Step-by-Step</option>
          </select>
        </div>
      </div>

      <label>Type your question (optional if you upload a photo)</label>
      <textarea name="q" placeholder="e.g., Solve 3x + 5 = 20 (show steps), or 'Explain deductibles vs premiums'"></textarea>

      <label>Or upload a photo (JPG/PNG) of your homework / document</label>
      <input type="file" name="photo" accept=".jpg,.jpeg,.png"/>

      <div class="row">
        <label class="pill" style="display:inline-flex;align-items:center;gap:8px">
          <input type="checkbox" name="coach" /> Coach Mode (one step at a time)
        </label>
        <div></div>
      </div>

      {% if not allowed %}
        <p class="warn">Daily free limit reached for your IP.{% if stripe_link %} <a href="{{stripe_link}}">Upgrade</a>.{% endif %}</p>
      {% endif %}

      <div class="row">
        <button {% if not allowed %}disabled{% endif %}>Get Help (Full Answer)</button>
        <button formaction="{{url_for('coach_start')}}" {% if not allowed %}disabled{% endif %}>Start Guided Session</button>
      </div>
    </form>
  </div>

  {% if answer %}
    <div class="card">
      <div class="answer">{{answer}}</div>
    </div>
  {% endif %}

  <div class="card">
    <h3>Create Printable Worksheet (PDF)</h3>
    <form method="post" action="/worksheet.pdf">
      <div class="row">
        <div>
          <label>Student name (optional)</label>
          <input type="text" name="student" placeholder="e.g., Jordan P."/>
        </div>
        <div></div>
      </div>
      <label>Problem</label>
      <textarea name="problem" placeholder="Paste the homework prompt here." required></textarea>
      <label>Guided Steps (paste from Coach Mode if you want)</label>
      <textarea name="steps" placeholder="1) ... 2) ... 3) ..."></textarea>
      <label>Final Answer</label>
      <textarea name="final" placeholder="x = 5 (or short final)"></textarea>
      <label>Why this answer is correct</label>
      <textarea name="why" placeholder="2–4 sentences explaining the core reason."></textarea>
      <label>Check Your Work</label>
      <textarea name="check" placeholder="A quick verification or substitution."></textarea>
      <button>Download PDF Worksheet</button>
    </form>
  </div>

  <div class="card">
    <h3>Fill a PDF Form (AcroForm)</h3>
    <form method="post" action="/fill-form.pdf" enctype="multipart/form-data">
      <label>Fillable PDF</label>
      <input type="file" name="pdf" accept=".pdf" required />
      <label>Answers (JSON) – optional</label>
      <textarea name="answers_json" placeholder='{"FirstName":"Jordan","LastName":"Lee","Phone":"555-123-4567"}'></textarea>
      <label>Answers (key=value per line) – optional</label>
      <textarea name="answers_lines" placeholder="FirstName=Jordan&#10;LastName=Lee&#10;Phone=555-123-4567"></textarea>
      <button>Download Filled PDF</button>
      <p class="fine">Tip: field names must match the PDF’s internal field names.</p>
    </form>
    <form method="post" action="/form-fields" enctype="multipart/form-data" style="margin-top:10px">
      <label>List form field names (optional helper)</label>
      <input type="file" name="pdf" accept=".pdf" />
      <button>List Fields</button>
    </form>
    {% if fields %}
      <div class="answer">{{fields}}</div>
    {% endif %}
  </div>

</main>
<footer>
  <span>Made for busy families & real life. | <a href="https://github.com/new">Fork & self-host</a></span>
  {% if stripe_link %} | <a href="{{stripe_link}}">Upgrade</a>{% endif %}
</footer>
</body></html>
"""

COACH_HTML = """
<!doctype html>
<html><head>
<meta charset="utf-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>Mini Assistant — Guided Session</title>
<link rel="icon" href="/static/favicon/favicon.ico">
<link rel="icon" type="image/png" sizes="32x32" href="/static/favicon/favicon-32x32.png">
<link rel="icon" type="image/png" sizes="192x192" href="/static/favicon/favicon-192x192.png">
<link rel="apple-touch-icon" href="/static/favicon/favicon-512x512.png">
<link rel="manifest" href="/static/manifest.json">
<style>
  body{margin:0;background:#0b0f14;color:#e8eef7;font:16px/1.5 system-ui,Segoe UI,Roboto,Inter,Helvetica,Arial}
  header{padding:20px;text-align:center;background:#0f1620;border-bottom:1px solid #1f2b3a}
  main{max-width:900px;margin:18px auto;padding:0 14px}
  .card{background:#101823;border:1px solid #1f2b3a;border-radius:14px;padding:16px;margin-bottom:14px}
  textarea,input,button{width:100%;padding:12px;border-radius:10px;border:1px solid #1f2b3a;background:#0a121a;color:#e8eef7}
  textarea{min-height:90px}
  .actions{display:flex;gap:10px;flex-wrap:wrap;margin-top:8px}
  button{background:#22c55e;color:#0b0f14;font-weight:800;cursor:pointer}
  .btn{flex:1}
  .answer{white-space:pre-wrap;background:#0b1118;border:1px solid #1f2b3a;border-radius:12px;padding:12px;margin-top:8px}
  a{color:#9ad1ff}
</style>
</head>
<body>
<header><h2>Mini Assistant — Guided Session</h2></header>
<main>
  {% if last_step %}
  <div class="card">
    <div class="answer">{{ last_step }}</div>
  </div>
  {% endif %}

  <div class="card">
    <form method="post" action="{{ url_for('coach_step') }}">
      <label>Your reply (optional)</label>
      <textarea name="student_reply" placeholder="e.g., 'I isolated x by subtracting 5'"></textarea>
      <input type="hidden" name="history" value="{{ history }}">
      <div class="actions">
        <button class="btn" name="action" value="next">Next Step</button>
        <button class="btn" name="action" value="hint" style="background:#3b82f6">Hint</button>
        <button class="btn" name="action" value="reveal" style="background:#ef4444">Reveal Final Answer</button>
      </div>
    </form>
  </div>

  <div class="card">
    <a href="{{ url_for('index') }}">← Back to Mini Assistant</a>
  </div>
</main>
</body></html>
"""

# ---------- routes ----------
@app.get("/")
def index():
    allowed = can_use_free()
    note = f"(Free: {FREE_DAILY_LIMIT}/day/IP)" if FREE_DAILY_LIMIT>0 else "(Unlimited demo)"
    return render_template_string(INDEX_HTML, app_name=APP_NAME, allowed=allowed, answer=None, limit_note=note, stripe_link=STRIPE_PAY_LINK, fields=None)

@app.post("/ask")
def ask():
    if not can_use_free(): return redirect(url_for("index"))
    subject = request.form.get("subject","Algebra I")
    mode    = request.form.get("mode","Kid")
    q_text  = (request.form.get("q") or "").strip()
    coach   = ("coach" in request.form)

    photo = request.files.get("photo")
    use_photo = photo and photo.filename.lower().endswith((".jpg",".jpeg",".png"))

    try:
        if use_photo:
            img_bytes = photo.read()
            msgs = build_vision_messages(subject, mode, img_bytes, photo.filename, q_text, coach)
        else:
            if not q_text: abort(400, "Type a question or upload a photo.")
            msgs = build_text_messages(subject, mode, q_text, coach)
        answer = call_openai_chat(msgs)
    except Exception as e:
        answer = f"Sorry — model error.\n\nDetails: {e}"

    bump_usage()
    note = f"(Free: {FREE_DAILY_LIMIT}/day/IP)" if FREE_DAILY_LIMIT>0 else "(Unlimited demo)"
    return render_template_string(INDEX_HTML, app_name=APP_NAME, allowed=can_use_free(), answer=answer, limit_note=note, stripe_link=STRIPE_PAY_LINK, fields=None)

@app.post("/coach/start")
def coach_start():
    if not can_use_free(): return redirect(url_for("index"))
    subject = request.form.get("subject","Algebra I")
    mode    = request.form.get("mode","Kid")
    q_text  = (request.form.get("q") or "").strip()
    photo = request.files.get("photo")
    data_url = None
    if photo and photo.filename.lower().endswith((".jpg",".jpeg",".png")):
        mime = "image/png" if photo.filename.lower().endswith(".png") else "image/jpeg"
        b64 = base64.b64encode(photo.read()).decode("utf-8")
        data_url = f"data:{mime};base64,{b64}"

    msgs = build_guided_messages(subject, mode, q_text, data_url, history=None)
    try:
        first = call_openai_chat(msgs)
    except Exception as e:
        first = f"Sorry — model error.\n\nDetails: {e}"
    msgs.append({"role":"assistant","content":first})
    hist = _pack_history(msgs)
    bump_usage()
    return render_template_string(COACH_HTML, last_step=first, history=hist)

@app.post("/coach/step")
def coach_step():
    history = _unpack_history(request.form.get("history",""))
    if not history:
        return render_template_string(COACH_HTML, last_step="Session expired. Start again.", history="")
    action = request.form.get("action","next")
    student_reply = (request.form.get("student_reply") or "").strip()
    steer = {
        "next":   "Please continue with EXACTLY ONE next step only, then ask ONE short question.",
        "hint":   "Please give a SMALL HINT only. Do not advance the solution yet.",
        "reveal": "Please now reveal the final solution concisely and include BOTH: (1) 'Why this answer is correct' in 2–4 sentences, and (2) 'Check Your Work' as a quick verification."
    }[action]
    if student_reply:
        history.append({"role":"user","content": f"Student reply: {student_reply}"})
    history.append({"role":"user","content": steer})
    try:
        out = call_openai_chat(history)
    except Exception as e:
        out = f"Sorry — model error.\n\nDetails: {e}"
    history.append({"role":"assistant","content": out})
    return render_template_string(COACH_HTML, last_step=out, history=_pack_history(history))

@app.post("/worksheet.pdf")
def worksheet_pdf():
    problem = (request.form.get("problem") or "").strip()
    steps   = (request.form.get("steps") or "").strip()
    answer  = (request.form.get("final") or "").strip()
    why     = (request.form.get("why") or "").strip()
    check   = (request.form.get("check") or "").strip()
    student = (request.form.get("student") or "").strip()
    if not problem: abort(400, "Problem text is required.")
    pdf_bytes = build_worksheet_pdf(problem, steps, answer, why, check, student)
    name = "worksheet.pdf" if not student else f"{student.replace(' ','_')}_worksheet.pdf"
    return send_file(pdf_bytes, as_attachment=True, download_name=name, mimetype="application/pdf")

@app.post("/fill-form.pdf")
def fill_form_pdf():
    pdf = request.files.get("pdf")
    if not pdf or not pdf.filename.lower().endswith(".pdf"):
        abort(400, "Upload a fillable PDF.")
    raw_json = (request.form.get("answers_json") or "").strip()
    raw_lines = (request.form.get("answers_lines") or "").strip()
    values = {}
    if raw_json:
        try:
            values.update(json.loads(raw_json))
        except Exception as e:
            abort(400, f"Invalid JSON: {e}")
    if raw_lines:
        for line in raw_lines.splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                values[k.strip()] = v.strip()
    if not values:
        abort(400, "Provide answers via JSON or key=value lines.")
    filled = fill_pdf_form(pdf.stream, values)
    name = pdf.filename.replace(".pdf","_filled.pdf")
    return send_file(filled, as_attachment=True, download_name=name, mimetype="application/pdf")

@app.post("/form-fields")
def form_fields():
    pdf = request.files.get("pdf")
    if not pdf or not pdf.filename.lower().endswith(".pdf"):
        allowed = can_use_free()
        note = f"(Free: {FREE_DAILY_LIMIT}/day/IP)" if FREE_DAILY_LIMIT>0 else "(Unlimited demo)"
        return render_template_string(INDEX_HTML, app_name=APP_NAME, allowed=allowed, answer=None, limit_note=note, stripe_link=STRIPE_PAY_LINK, fields="Upload a PDF to list fields.")
    fields = list_pdf_fields(pdf.stream)
    allowed = can_use_free()
    note = f"(Free: {FREE_DAILY_LIMIT}/day/IP)" if FREE_DAILY_LIMIT>0 else "(Unlimited demo)"
    return render_template_string(INDEX_HTML, app_name=APP_NAME, allowed=allowed, answer=None, limit_note=note, stripe_link=STRIPE_PAY_LINK, fields=json.dumps(fields, indent=2))

PRIVACY_HTML = """
<!doctype html><html><head>
<meta charset="utf-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>Mini Assistant — Privacy</title>
<link rel="icon" href="/static/favicon/favicon.ico">
<link rel="icon" type="image/png" sizes="32x32" href="/static/favicon/favicon-32x32.png">
<link rel="icon" type="image/png" sizes="192x192" href="/static/favicon/favicon-192x192.png">
<link rel="apple-touch-icon" href="/static/favicon/favicon-512x512.png">
<link rel="manifest" href="/static/manifest.json">
<style>
  body{margin:0;background:#0b0f14;color:#e8eef7;font:16px/1.6 system-ui,Segoe UI,Roboto,Inter,Helvetica,Arial}
  main{max-width:900px;margin:6vh auto;padding:0 16px}
  .card{background:#101823;border:1px solid #1f2b3a;border-radius:14px;padding:18px}
  h1{margin:0 0 12px 0}
  a{color:#9ad1ff}
</style>
</head><body>
<main>
  <div class="card">
    <h1>Privacy Policy</h1>
    <p>We store minimal data to run the app:</p>
    <ul>
      <li>IP/day count for free-usage limits (if enabled)</li>
      <li>Account email & password hash (only if you create an account)</li>
      <li>No worksheets, photos, or form PDFs are stored after processing</li>
    </ul>
    <p>Model requests are sent to OpenAI to generate answers. Do not upload sensitive information.</p>
    <p>Contact: support@example.com</p>
    <p><a href="/">← Back to app</a></p>
  </div>
</main>
</body></html>
"""

@app.get("/privacy")
def privacy():
    return PRIVACY_HTML

@app.route('/static/<path:filename>')
def static_files(filename):
    return send_from_directory('static', filename)

@app.get("/health")
def health():
    return {"ok": True, "app": APP_NAME, "model": MODEL, "vision": True}

if __name__ == "__main__":
    from waitress import serve
    serve(app, host="0.0.0.0", port=int(os.getenv("PORT","8080")))
