import os
from flask import Flask, render_template, redirect, url_for, request, session, flash, abort
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, login_required, logout_user, UserMixin, current_user
from flask_mail import Mail, Message
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime
from dotenv import load_dotenv
from flask_migrate import Migrate
from itsdangerous import URLSafeTimedSerializer
from werkzeug.security import generate_password_hash, check_password_hash
import atexit

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'defaultsecret')

# Database setup
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///pillpal.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Mail config
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = os.getenv("MAIL_USERNAME")
app.config['MAIL_PASSWORD'] = os.getenv("MAIL_PASSWORD")

# Twilio (mocked)
TWILIO_SID = os.getenv("TWILIO_SID")
TWILIO_AUTH = os.getenv("TWILIO_AUTH")
TWILIO_PHONE = os.getenv("TWILIO_PHONE")

# Extensions setup
db = SQLAlchemy(app)
migrate = Migrate(app, db)
mail = Mail(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
serializer = URLSafeTimedSerializer(app.secret_key)

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
    time = db.Column(db.String(10))
    status = db.Column(db.String(20), default='pending')
    member_id = db.Column(db.Integer, db.ForeignKey('family_member.id'), nullable=False)

# Login manager
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Routes
@app.route('/')
@login_required
def home():
    members = FamilyMember.query.filter_by(user_id=current_user.id).all()
    return render_template('dashboard.html', members=members)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form['email']
        password = generate_password_hash(request.form['password'])
        if User.query.filter_by(email=email).first():
            flash('Email already registered.')
            return redirect(url_for('register'))
        user = User(email=email, password=password)
        db.session.add(user)
        db.session.commit()
        flash('Registered! Now log in.')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(email=request.form['email']).first()
        if user and check_password_hash(user.password, request.form['password']):
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

# Password reset routes
@app.route('/reset_password', methods=['GET', 'POST'])
def reset_request():
    if current_user.is_authenticated:
        return redirect(url_for('home'))
    if request.method == 'POST':
        user = User.query.filter_by(email=request.form['email']).first()
        if user:
            token = serializer.dumps(user.email, salt='password-reset-salt')
            reset_url = url_for('reset_token', token=token, _external=True)
            body = f"Reset your password using the following link:\n{reset_url}"
            try:
                mail.send(Message("Password Reset Request", recipients=[user.email], body=body))
                flash("Password reset email sent.", 'info')
            except:
                flash("Failed to send email.", 'danger')
        else:
            flash("No account found with that email.", 'warning')
        return redirect(url_for('login'))
    return render_template('reset_request.html')

@app.route('/reset_password/<token>', methods=['GET', 'POST'])
def reset_token(token):
    if current_user.is_authenticated:
        return redirect(url_for('home'))
    try:
        email = serializer.loads(token, salt='password-reset-salt', max_age=3600)
    except:
        flash('Invalid or expired token.', 'warning')
        return redirect(url_for('reset_request'))
    user = User.query.filter_by(email=email).first()
    if not user:
        flash('User not found.', 'danger')
        return redirect(url_for('reset_request'))
    if request.method == 'POST':
        if request.form['password'] != request.form['confirm_password']:
            flash('Passwords do not match.', 'danger')
            return redirect(url_for('reset_token', token=token))
        user.password = generate_password_hash(request.form['password'])
        db.session.commit()
        flash('Your password has been reset!', 'success')
        return redirect(url_for('login'))
    return render_template('reset_token.html')

# Reminder system
def send_reminders():
    now = datetime.now().strftime("%H:%M")
    pills = Pill.query.filter_by(time=now, status='pending').all()
    for pill in pills:
        member = pill.member
        user = member.owner
        msg = f"Reminder: {member.name} should take {pill.name} now."

        # Send email
        if user.email:
            try:
                mail.send(Message('Pill Reminder', recipients=[user.email], body=msg))
            except Exception as e:
                print("Email failed:", e)

        # Mock SMS
        print(f"Mock SMS/WhatsApp to {member.phone}: {msg}")

        pill.status = 'done'
        db.session.commit()

scheduler = BackgroundScheduler()
scheduler.add_job(func=send_reminders, trigger="interval", seconds=60)
scheduler.start()
atexit.register(lambda: scheduler.shutdown())

if __name__ == '__main__':
    app.run(debug=True)
