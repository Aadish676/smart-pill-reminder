from flask import Flask, render_template, request, redirect, url_for, flash, abort
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import sqlite3
import os
import requests
import smtplib
from email.mime.text import MIMEText
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadSignature
from dotenv import load_dotenv
from apscheduler.schedulers.background import BackgroundScheduler

# Load environment variables
load_dotenv()

# Configuration
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY")
UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Email settings
SMTP_SERVER = 'smtp.gmail.com'
SMTP_PORT = 587
SENDER_EMAIL = os.getenv("EMAIL_USER")
SENDER_PASSWORD = os.getenv("EMAIL_PASS")

# Token Serializer
serializer = URLSafeTimedSerializer(app.secret_key)

# Flask-Login Setup
login_manager = LoginManager()
login_manager.login_view = 'login'
login_manager.init_app(app)

# OCR API key
OCR_API_KEY = 'helloworld'

# Database helpers
def get_db_connection():
    conn = sqlite3.connect('pills.db')
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS pills (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            name TEXT,
            time TEXT,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# User model
class User(UserMixin):
    def __init__(self, id_, username, email, password_hash):
        self.id = id_
        self.username = username
        self.email = email
        self.password_hash = password_hash

@login_manager.user_loader
def load_user(user_id):
    conn = get_db_connection()
    user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    if user:
        return User(user['id'], user['username'], user['email'], user['password_hash'])
    return None

# Email sender
def send_email(to_email, subject, body):
    msg = MIMEText(body)
    msg['Subject'] = subject
    msg['From'] = SENDER_EMAIL
    msg['To'] = to_email

    try:
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.sendmail(SENDER_EMAIL, to_email, msg.as_string())
        server.quit()
        print(f"Email sent to {to_email}")
    except Exception as e:
        print(f"Email failed: {e}")

# Pill reminder sender
def send_pill_reminder(to_email, pill_name, pill_time):
    subject = 'Pill Reminder'
    body = f"Reminder: Take your pill '{pill_name}' at {pill_time}."
    send_email(to_email, subject, body)

# Reminder scheduler task
def check_and_send_reminders():
    conn = get_db_connection()
    pills = conn.execute("SELECT pills.name, pills.time, users.email FROM pills JOIN users ON pills.user_id = users.id").fetchall()
    for pill in pills:
        send_pill_reminder(pill['email'], pill['name'], pill['time'])
    conn.close()

# Routes
@app.route('/')
@login_required
def index():
    conn = get_db_connection()
    pills = conn.execute("SELECT * FROM pills WHERE user_id = ? ORDER BY time", (current_user.id,)).fetchall()
    conn.close()
    return render_template('index.html', pills=pills)

@app.route('/add', methods=['POST'])
@login_required
def add_pill():
    name = request.form['pill_name']
    time = request.form['pill_time']
    conn = get_db_connection()
    conn.execute("INSERT INTO pills (user_id, name, time) VALUES (?, ?, ?)", (current_user.id, name, time))
    conn.commit()
    conn.close()
    flash("Pill added successfully!")
    return redirect(url_for('index'))

@app.route('/ocr', methods=['POST'])
@login_required
def ocr_extract():
    if 'prescription' not in request.files:
        flash("No file uploaded")
        return redirect(url_for('index'))

    file = request.files['prescription']
    if file.filename == '':
        flash("Empty filename")
        return redirect(url_for('index'))

    filename = secure_filename(file.filename)
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(filepath)

    with open(filepath, 'rb') as img:
        response = requests.post(
            'https://api.ocr.space/parse/image',
            files={'filename': img},
            data={'apikey': OCR_API_KEY, 'language': 'eng'}
        )

    try:
        result = response.json()
        text = result['ParsedResults'][0]['ParsedText']
        lines = [line.strip() for line in text.split('\n') if line.strip()]
    except Exception as e:
        lines = [f"OCR failed: {str(e)}"]

    conn = get_db_connection()
    pills = conn.execute("SELECT * FROM pills WHERE user_id = ? ORDER BY time", (current_user.id,)).fetchall()
    conn.close()

    return render_template("index.html", pills=pills, ocr_lines=lines)

# Authentication routes
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username'].strip()
        email = request.form['email'].strip()
        password = request.form['password']

        conn = get_db_connection()
        existing_user = conn.execute("SELECT * FROM users WHERE username = ? OR email = ?", (username, email)).fetchone()
        if existing_user:
            flash('Username or email already taken')
            conn.close()
            return redirect(url_for('register'))

        password_hash = generate_password_hash(password)
        conn.execute("INSERT INTO users (username, email, password_hash) VALUES (?, ?, ?)", (username, email, password_hash))
        conn.commit()
        conn.close()
        flash('Registration successful! Please login.')
        return redirect(url_for('login'))

    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password']

        conn = get_db_connection()
        user = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        conn.close()

        if user and check_password_hash(user['password_hash'], password):
            user_obj = User(user['id'], user['username'], user['email'], user['password_hash'])
            login_user(user_obj)
            flash('Logged in successfully!')
            return redirect(url_for('index'))
        else:
            flash('Invalid username or password')
            return redirect(url_for('login'))

    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Logged out.')
    return redirect(url_for('login'))

# Password reset
@app.route('/reset_request', methods=['GET', 'POST'])
def reset_request():
    if request.method == 'POST':
        email = request.form['email'].strip()
        conn = get_db_connection()
        user = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        conn.close()
        if user:
            token = serializer.dumps(email, salt='password-reset-salt')
            reset_url = url_for('reset_token', token=token, _external=True)
            body = f"To reset your password, click this link:\n\n{reset_url}"
            send_email(email, "Password Reset Request", body)
            flash('Password reset email sent! Check your inbox.')
        else:
            flash('Email not found.')
        return redirect(url_for('login'))
    return render_template('reset_request.html')

@app.route('/reset_password/<token>', methods=['GET', 'POST'])
def reset_token(token):
    try:
        email = serializer.loads(token, salt='password-reset-salt', max_age=3600)
    except (SignatureExpired, BadSignature):
        flash('The reset link is invalid or has expired.')
        return redirect(url_for('reset_request'))

    if request.method == 'POST':
        password = request.form['password']
        password_hash = generate_password_hash(password)
        conn = get_db_connection()
        conn.execute("UPDATE users SET password_hash = ? WHERE email = ?", (password_hash, email))
        conn.commit()
        conn.close()
        flash('Password has been reset. You can now log in.')
        return redirect(url_for('login'))

    return render_template('reset_password.html')

# Scheduler
scheduler = BackgroundScheduler()
scheduler.add_job(func=check_and_send_reminders, trigger="interval", seconds=60)
scheduler.start()

# Run app
if __name__ == '__main__':
    app.run(debug=True)


