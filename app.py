from flask import Flask, render_template, request, redirect, url_for, flash, session, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, logout_user, login_required, current_user, UserMixin
from flask_mail import Mail, Message
from flask_migrate import Migrate
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime
from werkzeug.utils import secure_filename
import os
from dotenv import load_dotenv
from twilio.rest import Client

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv("SECRET_KEY", "dev")
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///pillpal.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

UPLOAD_FOLDER = os.path.join(os.getcwd(), 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = os.getenv("MAIL_USERNAME")
app.config['MAIL_PASSWORD'] = os.getenv("MAIL_PASSWORD")
mail = Mail(app)

TWILIO_SID = os.getenv("TWILIO_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH")
TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE")
twilio_client = Client(TWILIO_SID, TWILIO_AUTH_TOKEN)

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
migrate = Migrate(app, db)

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)
    reset_token = db.Column(db.String(120), nullable=True)
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
    time = db.Column(db.String(10))
    status = db.Column(db.String(20), default='pending')
    member_id = db.Column(db.Integer, db.ForeignKey('family_member.id'), nullable=False)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@app.route('/')
@login_required
def home():
    members = FamilyMember.query.filter_by(user_id=current_user.id).all()
    return render_template('dashboard.html', members=members)

@app.route('/test_notification')
@login_required
def test_notification():
    now = datetime.now().strftime("%H:%M:%S")
    member = FamilyMember.query.filter_by(user_id=current_user.id).first()
    if not member:
        return "No family member found for test.", 400

    msg_body = f"[{now}] Test notification for {member.name}"
    results = []

    if current_user.email:
        try:
            mail.send(Message('Test Pill Reminder', recipients=[current_user.email], body=msg_body))
            results.append(f"Email sent to {current_user.email}")
        except Exception as e:
            results.append(f"Email failed: {e}")

    try:
        to_number = f"whatsapp:{member.phone}" if TWILIO_PHONE_NUMBER.startswith("whatsapp:") else member.phone
        twilio_client.messages.create(to=to_number, from_=TWILIO_PHONE_NUMBER, body=msg_body)
        results.append(f"Twilio message sent to {to_number}")
    except Exception as e:
        results.append(f"Twilio failed: {e}")

    return "<br>".join(results)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        if User.query.filter_by(email=email).first():
            flash('Email already registered.')
            return redirect(url_for('register'))
        db.session.add(User(email=email, password=password))
        db.session.commit()
        flash('Registered successfully.')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(email=request.form['email']).first()
        if user and user.password == request.form['password']:
            login_user(user)
            return redirect(url_for('home'))
        flash('Invalid credentials.')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/add_member', methods=['POST'])
@login_required
def add_member():
    member = FamilyMember(name=request.form['name'], phone=request.form['phone'], relation=request.form['relation'], user_id=current_user.id)
    db.session.add(member)
    db.session.commit()
    return redirect(url_for('home'))

@app.route('/add_pill/<int:member_id>', methods=['POST'])
@login_required
def add_pill(member_id):
    pill = Pill(name=request.form['pill_name'], time=request.form['pill_time'], member_id=member_id)
    db.session.add(pill)
    db.session.commit()
    return redirect(url_for('home'))

@app.route('/upload_prescription', methods=['POST'])
@login_required
def upload_prescription():
    file = request.files['prescription']
    if file:
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        flash('Prescription uploaded for OCR (mocked).')
        return redirect(url_for('home'))
    flash('File upload failed.')
    return redirect(url_for('home'))

@app.route('/reset_request', methods=['GET', 'POST'])
def reset_request():
    if request.method == 'POST':
        user = User.query.filter_by(email=request.form['email']).first()
        if user:
            user.reset_token = os.urandom(8).hex()
            db.session.commit()
            reset_url = url_for('reset_password', token=user.reset_token, _external=True)
            mail.send(Message("Password Reset", recipients=[user.email], body=f"Reset here: {reset_url}"))
            flash('Reset link sent.')
        else:
            flash('Email not found.')
        return redirect(url_for('login'))
    return render_template('reset_request.html')

@app.route('/reset_password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    user = User.query.filter_by(reset_token=token).first()
    if not user:
        flash('Invalid or expired token.')
        return redirect(url_for('login'))
    if request.method == 'POST':
        user.password = request.form['password']
        user.reset_token = None
        db.session.commit()
        flash('Password updated.')
        return redirect(url_for('login'))
    return render_template('reset_password.html')

scheduler = BackgroundScheduler()

@scheduler.scheduled_job('interval', seconds=60)
def send_reminders():
    with app.app_context():
        now = datetime.now().strftime("%H:%M")
        print(f"[{now}] Scheduler checked.")
        due_pills = Pill.query.filter_by(time=now, status='pending').all()
        if not due_pills:
            print(f"[{now}] No pills due.")
            return
        for pill in due_pills:
            member = pill.member
            user = member.owner
            msg_body = f"Reminder: {member.name} should take {pill.name} now."

            if user.email:
                try:
                    mail.send(Message('Pill Reminder', recipients=[user.email], body=msg_body))
                    print(f"[{now}] Email sent to {user.email}")
                except Exception as e:
                    print(f"[{now}] Email failed for {user.email}: {e}")

            if member.phone:
                try:
                    to_number = f"whatsapp:{member.phone}" if TWILIO_PHONE_NUMBER.startswith("whatsapp:") else member.phone
                    twilio_client.messages.create(to=to_number, from_=TWILIO_PHONE_NUMBER, body=msg_body)
                    print(f"[{now}] Twilio message sent to {to_number}")
                except Exception as e:
                    print(f"[{now}] Twilio send failed to {member.phone}: {e}")

            try:
                pill.status = 'done'
                db.session.commit()
            except Exception as e:
                print(f"[{now}] Error updating status for {pill.name}: {e}")

with app.app_context():
    db.create_all()

scheduler.start()

if __name__ == '__main__':
    app.run(debug=True)

