import os
from flask import Flask, render_template, redirect, url_for, request, session, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, login_required, logout_user, UserMixin, current_user
from flask_mail import Mail, Message
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime
from dotenv import load_dotenv
from flask_migrate import Migrate, upgrade
import atexit

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'defaultsecret')

# Database setup
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///pillpal.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Migrate support
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

# Routes and other code ...

# Reminder function and scheduler ...

# Shutdown scheduler properly
atexit.register(lambda: scheduler.shutdown())

# Run the migrations only when running locally directly
if __name__ == '__main__':
    with app.app_context():
        upgrade()  # This runs your migration scripts and creates tables if needed
    app.run(debug=True)
