from flask import Flask, render_template, redirect, request, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, login_required, logout_user, UserMixin, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from apscheduler.schedulers.background import BackgroundScheduler
from dotenv import load_dotenv
import os
import datetime

# Load .env
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "devsecret")
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///pillpal.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Init extensions
db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# Mock notification functions
def send_sms_mock(phone, message):
    print(f"[MOCK SMS to {phone}] {message}")

def send_whatsapp_mock(phone, message):
    print(f"[MOCK WhatsApp to {phone}] {message}")

def send_email_mock(email, subject, body):
    print(f"[MOCK Email to {email}] Subject: {subject}\n{body}")

# Models
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True)
    email = db.Column(db.String(128), unique=True)
    password_hash = db.Column(db.String(256))
    family_members = db.relationship('FamilyMember', backref='user', lazy=True)

class FamilyMember(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    name = db.Column(db.String(64))
    phone = db.Column(db.String(20))
    notify_method = db.Column(db.String(20))  # email, sms, whatsapp
    pills = db.relationship('Pill', backref='member', lazy=True)

class Pill(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    member_id = db.Column(db.Integer, db.ForeignKey('family_member.id'), nullable=False)
    name = db.Column(db.String(100))
    time = db.Column(db.String(10))  # Format: HH:MM
    status = db.Column(db.String(20), default='pending')

# Login loader
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Routes
@app.route('/')
@login_required
def dashboard():
    members = current_user.family_members
    return render_template('dashboard.html', members=members)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        user = User(username=request.form['username'], email=request.form['email'],
                    password_hash=generate_password_hash(request.form['password']))
        db.session.add(user)
        db.session.commit()
        flash("Registration successful")
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form['username']).first()
        if user and check_password_hash(user.password_hash, request.form['password']):
            login_user(user)
            return redirect(url_for('dashboard'))
        flash("Invalid credentials")
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
        user_id=current_user.id,
        name=request.form['name'],
        phone=request.form['phone'],
        notify_method=request.form['notify']
    )
    db.session.add(member)
    db.session.commit()
    return redirect(url_for('dashboard'))

@app.route('/add_pill/<int:member_id>', methods=['POST'])
@login_required
def add_pill(member_id):
    pill = Pill(
        member_id=member_id,
        name=request.form['pill_name'],
        time=request.form['pill_time']
    )
    db.session.add(pill)
    db.session.commit()
    return redirect(url_for('dashboard'))

# Scheduler to send reminders
from apscheduler.schedulers.background import BackgroundScheduler

scheduler = BackgroundScheduler()
scheduler.start()
@scheduler.scheduled_job('interval', minutes=1)
def send_reminders():
    with app.app_context():
        now = datetime.datetime.now().strftime('%H:%M')
        pills = Pill.query.filter_by(time=now, status='pending').all()
        for pill in pills:
            member = pill.member
            msg = f"Reminder: {member.name}, take your pill: {pill.name} at {pill.time}."
            if member.notify_method == 'email':
                send_email_mock(member.user.email, "Pill Reminder", msg)
            elif member.notify_method == 'sms':
                send_sms_mock(member.phone, msg)
            elif member.notify_method == 'whatsapp':
                send_whatsapp_mock(member.phone, msg)
            pill.status = 'notified'
        db.session.commit()
        db.session.commit()



# DB init
with app.app_context():
    db.create_all()

# Run
if __name__ == '__main__':
    app.run(debug=True)


