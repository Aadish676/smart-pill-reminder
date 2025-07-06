import os
import datetime
from flask import Flask, render_template, request, redirect, url_for, session
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, login_required, logout_user, UserMixin, current_user
from dotenv import load_dotenv
from apscheduler.schedulers.background import BackgroundScheduler
from email.mime.text import MIMEText
import smtplib
from twilio.rest import Client

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'defaultsecret')

# Configure DB
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///pill_reminder.db'
db = SQLAlchemy(app)

# Login Manager
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Scheduler
scheduler = BackgroundScheduler()
scheduler.start()

# Twilio Setup
twilio_sid = os.getenv('TWILIO_ACCOUNT_SID')
twilio_token = os.getenv('TWILIO_AUTH_TOKEN')
twilio_number = os.getenv('TWILIO_PHONE_NUMBER')
twilio_client = Client(twilio_sid, twilio_token)


# Models
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(100), unique=True)
    password = db.Column(db.String(100))
    family_members = db.relationship('FamilyMember', backref='user')


class FamilyMember(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    phone = db.Column(db.String(20))
    notify_method = db.Column(db.String(10))  # email, sms, whatsapp
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    pills = db.relationship('Pill', backref='member')


class Pill(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    time = db.Column(db.String(5))  # Format: "HH:MM"
    status = db.Column(db.String(20), default='pending')
    member_id = db.Column(db.Integer, db.ForeignKey('family_member.id'))


# Email sender
def send_email(to, subject, body):
    msg = MIMEText(body)
    msg['Subject'] = subject
    msg['From'] = os.getenv('EMAIL_USER')
    msg['To'] = to
    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(os.getenv('EMAIL_USER'), os.getenv('EMAIL_PASS'))
            server.send_message(msg)
    except Exception as e:
        print("Email error:", e)


# SMS and WhatsApp sender
def send_sms(to, message):
    try:
        twilio_client.messages.create(
            body=message,
            from_=twilio_number,
            to=to
        )
    except Exception as e:
        print("SMS error:", e)


def send_whatsapp(to, message):
    try:
        full_to = f'whatsapp:{to}' if not to.startswith('whatsapp:') else to
        twilio_client.messages.create(
            body=message,
            from_='whatsapp:' + twilio_number,
            to=full_to
        )
    except Exception as e:
        print("WhatsApp error:", e)


@scheduler.scheduled_job('interval', minutes=1)
def send_reminders():
    with app.app_context():
        now = datetime.datetime.now().strftime('%H:%M')
        pills = Pill.query.filter_by(time=now, status='pending').all()
        for pill in pills:
            member = pill.member
            msg = f"Hi {member.name}, reminder to take your pill: {pill.name} at {pill.time}."
            if member.notify_method == 'email':
                send_email(current_user.email, "Pill Reminder", msg)
            elif member.notify_method == 'sms':
                send_sms(member.phone, msg)
            elif member.notify_method == 'whatsapp':
                send_whatsapp(member.phone, msg)
            pill.status = 'notified'
        db.session.commit()


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# Routes

@app.route('/')
@login_required
def dashboard():
    members = current_user.family_members
    return render_template('dashboard.html', members=members)


@app.route('/add_member', methods=['POST'])
@login_required
def add_member():
    name = request.form['name']
    phone = request.form['phone']
    method = request.form['notify_method']
    member = FamilyMember(name=name, phone=phone, notify_method=method, user=current_user)
    db.session.add(member)
    db.session.commit()
    return redirect(url_for('dashboard'))


@app.route('/assign_pill/<int:member_id>', methods=['POST'])
@login_required
def assign_pill(member_id):
    name = request.form['pill_name']
    time = request.form['pill_time']
    pill = Pill(name=name, time=time, member_id=member_id)
    db.session.add(pill)
    db.session.commit()
    return redirect(url_for('dashboard'))


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        if User.query.filter_by(email=email).first():
            return "Email already registered"
        user = User(email=email, password=password)
        db.session.add(user)
        db.session.commit()
        login_user(user)
        return redirect(url_for('dashboard'))
    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(email=request.form['email']).first()
        if user and user.password == request.form['password']:
            login_user(user)
            return redirect(url_for('dashboard'))
        return "Invalid login"
    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)



