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

# Upload settings for OCR
UPLOAD_FOLDER = os.path.join(os.getcwd(), 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Email settings
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = os.getenv("MAIL_USERNAME")
app.config['MAIL_PASSWORD'] = os.getenv("MAIL_PASSWORD")
mail = Mail(app)

# Twilio settings
TWILIO_SID = os.getenv("TWILIO_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH")
TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE")
twilio_client = Client(TWILIO_SID, TWILIO_AUTH_TOKEN)

# App extensions
db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
migrate = Migrate(app, db)

# Models
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
    time = db.Column(db.String(10))  # HH:MM
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

# Background job
scheduler = BackgroundScheduler()

@scheduler.scheduled_job('interval', seconds=60)
def send_reminders():
    with app.app_context():
        now = datetime.now().strftime("%H:%M")
        due_pills = Pill.query.filter_by(time=now, status='pending').all()
        for pill in due_pills:
            member = pill.member
            user = member.owner
            msg_body = f"Reminder: {member.name} should take {pill.name} now."

            # Email
            if user.email:
                try:
                    mail.send(Message('Pill Reminder', recipients=[user.email], body=msg_body))
                except Exception as e:
                    print("Email failed:", e)

            # WhatsApp/SMS
            try:
                twilio_client.messages.create(
                    to=f"whatsapp:{member.phone}",  # or just phone for SMS
                    from_=f"whatsapp:{TWILIO_PHONE_NUMBER}",
                    body=msg_body
                )
            except Exception as e:
                print("Twilio send failed:", e)

            pill.status = 'done'
            db.session.commit()

# Create tables BEFORE starting scheduler
with app.app_context():
    db.create_all()

scheduler.start()

if __name__ == '__main__':
    app.run(debug=True)

