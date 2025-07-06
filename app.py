import os
from flask import Flask, render_template, redirect, url_for, request, session, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, login_required, logout_user, UserMixin, current_user
from flask_mail import Mail, Message
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime
from dotenv import load_dotenv
from flask_migrate import Migrate
from yourapp import app, db  # adjust import to your app structure

migrate = Migrate(app, db)

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'defaultsecret')

# Database setup
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///pillpal.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Migrate support
from flask_migrate import Migrate
migrate = Migrate(app, db)

# Flask-Login setup
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Mail config
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = os.getenv("MAIL_USERNAME")
app.config['MAIL_PASSWORD'] = os.getenv("MAIL_PASSWORD")
mail = Mail(app)

# Twilio (mocked for now)
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
    time = db.Column(db.String(10))  # in HH:MM format
    status = db.Column(db.String(20), default='pending')
    member_id = db.Column(db.Integer, db.ForeignKey('family_member.id'), nullable=False)

# Flask-Login loader
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
        password = request.form['password']
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
        if user and user.password == request.form['password']:
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
    name = request.form['name']
    phone = request.form['phone']
    relation = request.form['relation']
    member = FamilyMember(name=name, phone=phone, relation=relation, user_id=current_user.id)
    db.session.add(member)
    db.session.commit()
    return redirect(url_for('home'))

@app.route('/add_pill/<int:member_id>', methods=['POST'])
@login_required
def add_pill(member_id):
    name = request.form['pill_name']
    time = request.form['pill_time']
    pill = Pill(name=name, time=time, member_id=member_id)
    db.session.add(pill)
    db.session.commit()
    return redirect(url_for('home'))

# Reminder function
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
                print("Email send failed:", e)

        # Mock Twilio send
        print(f"Would send SMS/WhatsApp to {member.phone}: {msg}")

        pill.status = 'done'
        db.session.commit()

# Schedule task every minute
scheduler = BackgroundScheduler()
scheduler.add_job(func=send_reminders, trigger="interval", seconds=60)
scheduler.start()

# Shutdown properly on exit
import atexit
atexit.register(lambda: scheduler.shutdown())

# Run only if not imported
if __name__ == '__main__':
    app.run(debug=True)



