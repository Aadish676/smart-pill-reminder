import os
from flask import Flask, render_template, redirect, url_for, request, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, logout_user, login_required, current_user, UserMixin
from flask_mail import Mail, Message
from apscheduler.schedulers.background import BackgroundScheduler
from dotenv import load_dotenv
from datetime import datetime
import atexit

# Load environment variables
load_dotenv()

# Flask app init
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "defaultsecret")
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///pillpal.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Mail config
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = os.getenv("MAIL_USERNAME")
app.config['MAIL_PASSWORD'] = os.getenv("MAIL_PASSWORD")
mail = Mail(app)

# DB + Login Manager
db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# Mock Twilio creds
TWILIO_SID = os.getenv("TWILIO_SID")
TWILIO_AUTH = os.getenv("TWILIO_AUTH")
TWILIO_PHONE = os.getenv("TWILIO_PHONE")

# Models
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(150), nullable=False)
    family_members = db.relationship('FamilyMember', backref='owner', lazy=True)

class FamilyMember(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    phone = db.Column(db.String(20))
    relation = db.Column(db.String(100))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    pills = db.relationship('Pill', backref='member', lazy=True)

class Pill(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    time = db.Column(db.String(10))  # Format: HH:MM
    status = db.Column(db.String(20), default='pending')
    member_id = db.Column(db.Integer, db.ForeignKey('family_member.id'), nullable=False)

# User loader
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# -------------------- Routes ----------------------

@app.route('/')
@login_required
def home():
    members = FamilyMember.query.filter_by(user_id=current_user.id).all()
    return render_template('dashboard.html', members=members)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        if User.query.filter_by(email=email).first():
            flash('Email already registered.')
            return redirect(url_for('register'))
        new_user = User(email=email, password=password)
        db.session.add(new_user)
        db.session.commit()
        flash('Registered successfully!')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        user = User.query.filter_by(email=email).first()
        if user and user.password == password:
            login_user(user)
            return redirect(url_for('home'))
        flash('Invalid credentials')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/add_member', methods=['POST'])
@login_required
def add_member():
    member = FamilyMember(
        name=request.form['name'],
        phone=request.form['phone'],
        relation=request.form['relation'],
        user_id=current_user.id
    )
    db.session.add(member)
    db.session.commit()
    return redirect(url_for('home'))

@app.route('/add_pill/<int:member_id>', methods=['POST'])
@login_required
def add_pill(member_id):
    pill = Pill(
        name=request.form['pill_name'],
        time=request.form['pill_time'],
        member_id=member_id
    )
    db.session.add(pill)
    db.session.commit()
    return redirect(url_for('home'))

# -------------------- Reminder Function ----------------------

def send_reminders():
    now = datetime.now().strftime("%H:%M")
    due_pills = Pill.query.filter_by(time=now, status='pending').all()
    for pill in due_pills:
        user = pill.member.owner
        msg_body = f"Reminder: {pill.member.name} should take {pill.name} now."
        
        # Email
        if user.email:
            try:
                msg = Message("Pill Reminder", recipients=[user.email], body=msg_body)
                mail.send(msg)
            except Exception as e:
                print("Failed to send email:", e)

        # Mock Twilio
        print(f"Would send WhatsApp/SMS to {pill.member.phone}: {msg_body}")

        pill.status = 'done'
        db.session.commit()

# Scheduler
scheduler = BackgroundScheduler()
scheduler.add_job(send_reminders, 'interval', seconds=60)
scheduler.start()
atexit.register(lambda: scheduler.shutdown())

# -------------------- DB Init Route (Temporary) ----------------------

@app.route('/init_db')
def init_db():
    db.create_all()
    return "✅ Database initialized successfully!"

# -------------------- Main ----------------------

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
