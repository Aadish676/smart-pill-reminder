from flask import Flask, render_template, request, redirect, url_for, flash, session, send_from_directory, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, logout_user, login_required, current_user, UserMixin
from flask_mail import Mail, Message
from flask_migrate import Migrate
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime, timedelta, time as dt_time
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
import os
from dotenv import load_dotenv
from twilio.rest import Client
import json

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv("SECRET_KEY", "dev-secret-key-change-in-production")
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'sqlite:///pillpal.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

UPLOAD_FOLDER = os.path.join(os.getcwd(), 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Email configuration
app.config['MAIL_SERVER'] = os.getenv('MAIL_SERVER', 'smtp.gmail.com')
app.config['MAIL_PORT'] = int(os.getenv('MAIL_PORT', 587))
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = os.getenv("MAIL_USERNAME")
app.config['MAIL_PASSWORD'] = os.getenv("MAIL_PASSWORD")
mail = Mail(app)

# Twilio configuration
TWILIO_SID = os.getenv("TWILIO_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH")
TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE")
twilio_client = Client(TWILIO_SID, TWILIO_AUTH_TOKEN) if TWILIO_SID and TWILIO_AUTH_TOKEN else None

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
migrate = Migrate(app, db)

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    first_name = db.Column(db.String(50), nullable=False)
    last_name = db.Column(db.String(50), nullable=False)
    phone = db.Column(db.String(20), nullable=True)
    timezone = db.Column(db.String(50), default='UTC')
    email_notifications = db.Column(db.Boolean, default=True)
    sms_notifications = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    reset_token = db.Column(db.String(120), nullable=True)
    family_members = db.relationship('FamilyMember', backref='owner', lazy=True, cascade='all, delete-orphan')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"

class FamilyMember(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20), nullable=True)
    email = db.Column(db.String(120), nullable=True)
    relation = db.Column(db.String(100), nullable=False)
    date_of_birth = db.Column(db.Date, nullable=True)
    medical_conditions = db.Column(db.Text, nullable=True)
    allergies = db.Column(db.Text, nullable=True)
    emergency_contact = db.Column(db.String(20), nullable=True)
    profile_image = db.Column(db.String(200), nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    medications = db.relationship('Medication', backref='patient', lazy=True, cascade='all, delete-orphan')
    medication_logs = db.relationship('MedicationLog', backref='patient', lazy=True, cascade='all, delete-orphan')

    @property
    def age(self):
        if self.date_of_birth:
            today = datetime.now().date()
            return today.year - self.date_of_birth.year - ((today.month, today.day) < (self.date_of_birth.month, self.date_of_birth.day))
        return None

class Medication(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    generic_name = db.Column(db.String(200), nullable=True)
    dosage = db.Column(db.String(50), nullable=False)  # e.g., "10mg", "2 tablets"
    form = db.Column(db.String(50), nullable=False)  # tablet, capsule, liquid, injection
    instructions = db.Column(db.Text, nullable=True)  # Special instructions
    prescribing_doctor = db.Column(db.String(100), nullable=True)
    prescription_date = db.Column(db.Date, nullable=True)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=True)  # None for ongoing medications
    total_quantity = db.Column(db.Integer, nullable=True)  # Total pills/doses prescribed
    remaining_quantity = db.Column(db.Integer, nullable=True)  # Pills remaining
    refill_reminder_threshold = db.Column(db.Integer, default=5)  # Alert when <= this many left
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    member_id = db.Column(db.Integer, db.ForeignKey('family_member.id'), nullable=False)
    schedules = db.relationship('MedicationSchedule', backref='medication', lazy=True, cascade='all, delete-orphan')
    logs = db.relationship('MedicationLog', backref='medication', lazy=True, cascade='all, delete-orphan')

class MedicationSchedule(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    time = db.Column(db.Time, nullable=False)  # Time to take medication
    frequency = db.Column(db.String(20), nullable=False)  # daily, weekly, monthly, as_needed
    frequency_details = db.Column(db.String(100), nullable=True)  # e.g., "Mon,Wed,Fri" for weekly
    meal_timing = db.Column(db.String(20), nullable=True)  # before_meal, with_meal, after_meal, empty_stomach
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    medication_id = db.Column(db.Integer, db.ForeignKey('medication.id'), nullable=False)

class MedicationLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    scheduled_time = db.Column(db.DateTime, nullable=False)
    taken_time = db.Column(db.DateTime, nullable=True)
    status = db.Column(db.String(20), default='pending')  # pending, taken, missed, skipped
    notes = db.Column(db.Text, nullable=True)
    side_effects = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    medication_id = db.Column(db.Integer, db.ForeignKey('medication.id'), nullable=False)
    member_id = db.Column(db.Integer, db.ForeignKey('family_member.id'), nullable=False)
    schedule_id = db.Column(db.Integer, db.ForeignKey('medication_schedule.id'), nullable=True)

class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    member_id = db.Column(db.Integer, db.ForeignKey('family_member.id'), nullable=False)
    medication_id = db.Column(db.Integer, db.ForeignKey('medication.id'), nullable=False)
    notification_type = db.Column(db.String(20), nullable=False)  # reminder, missed, refill, emergency
    message = db.Column(db.Text, nullable=False)
    scheduled_time = db.Column(db.DateTime, nullable=False)
    sent_time = db.Column(db.DateTime, nullable=True)
    delivery_method = db.Column(db.String(20), nullable=False)  # email, sms, both
    status = db.Column(db.String(20), default='pending')  # pending, sent, failed
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# Legacy Pill model for backward compatibility - will be migrated
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
    members = FamilyMember.query.filter_by(user_id=current_user.id, is_active=True).all()
    
    # Get today's medication schedule for all family members
    today = datetime.now().date()
    today_medications = []
    
    for member in members:
        for medication in member.medications:
            if medication.is_active:
                for schedule in medication.schedules:
                    if schedule.is_active:
                        # Check if medication should be taken today based on frequency
                        if should_take_today(schedule, today):
                            # Check if already logged for today
                            existing_log = MedicationLog.query.filter_by(
                                medication_id=medication.id,
                                member_id=member.id,
                                schedule_id=schedule.id
                            ).filter(
                                MedicationLog.scheduled_time >= datetime.combine(today, dt_time.min),
                                MedicationLog.scheduled_time < datetime.combine(today, dt_time.max)
                            ).first()
                            
                            if not existing_log:
                                # Create pending log entry
                                scheduled_datetime = datetime.combine(today, schedule.time)
                                log = MedicationLog(
                                    medication_id=medication.id,
                                    member_id=member.id,
                                    schedule_id=schedule.id,
                                    scheduled_time=scheduled_datetime,
                                    status='pending'
                                )
                                db.session.add(log)
                                today_medications.append({
                                    'log': log,
                                    'member': member,
                                    'medication': medication,
                                    'schedule': schedule
                                })
                            else:
                                today_medications.append({
                                    'log': existing_log,
                                    'member': member,
                                    'medication': medication,
                                    'schedule': schedule
                                })
    
    db.session.commit()
    
    # Get recent medication logs for dashboard
    recent_logs = MedicationLog.query.join(FamilyMember).filter(
        FamilyMember.user_id == current_user.id
    ).order_by(MedicationLog.scheduled_time.desc()).limit(10).all()
    
    # Get medications needing refill
    low_stock_medications = []
    for member in members:
        for medication in member.medications:
            if (medication.is_active and 
                medication.remaining_quantity is not None and 
                medication.remaining_quantity <= medication.refill_reminder_threshold):
                low_stock_medications.append({
                    'medication': medication,
                    'member': member
                })
    
    return render_template('dashboard.html', 
                         members=members, 
                         today_medications=today_medications,
                         recent_logs=recent_logs,
                         low_stock_medications=low_stock_medications)

def should_take_today(schedule, target_date):
    """Check if medication should be taken on the target date based on schedule frequency"""
    if schedule.frequency == 'daily':
        return True
    elif schedule.frequency == 'weekly':
        if schedule.frequency_details:
            # Format: "Mon,Wed,Fri" or "1,3,5" (weekday numbers)
            days = schedule.frequency_details.split(',')
            current_day = target_date.strftime('%a')  # Mon, Tue, etc.
            current_day_num = str(target_date.weekday())  # 0=Monday, 6=Sunday
            return current_day in days or current_day_num in days
        return True  # Default to daily if no details
    elif schedule.frequency == 'as_needed':
        return False  # Only when manually logged
    return True  # Default case

@app.route('/member/<int:member_id>')
@login_required
def member_detail(member_id):
    member = FamilyMember.query.filter_by(id=member_id, user_id=current_user.id).first_or_404()
    
    # Get medication history for the past 30 days
    thirty_days_ago = datetime.now() - timedelta(days=30)
    medication_logs = MedicationLog.query.filter_by(member_id=member_id).filter(
        MedicationLog.scheduled_time >= thirty_days_ago
    ).order_by(MedicationLog.scheduled_time.desc()).all()
    
    # Calculate adherence rate
    total_scheduled = MedicationLog.query.filter_by(member_id=member_id).filter(
        MedicationLog.scheduled_time >= thirty_days_ago
    ).count()
    
    taken_count = MedicationLog.query.filter_by(member_id=member_id, status='taken').filter(
        MedicationLog.scheduled_time >= thirty_days_ago
    ).count()
    
    adherence_rate = (taken_count / total_scheduled * 100) if total_scheduled > 0 else 0
    
    return render_template('member_detail.html', 
                         member=member, 
                         medication_logs=medication_logs,
                         adherence_rate=adherence_rate)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        first_name = request.form['first_name']
        last_name = request.form['last_name']
        phone = request.form.get('phone', '')
        
        if User.query.filter_by(email=email).first():
            flash('Email already registered.')
            return redirect(url_for('register'))
        
        user = User(
            email=email,
            first_name=first_name,
            last_name=last_name,
            phone=phone
        )
        user.set_password(password)
        
        db.session.add(user)
        db.session.commit()
        flash('Registered successfully.')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(email=request.form['email']).first()
        if user and user.check_password(request.form['password']):
            login_user(user)
            return redirect(url_for('home'))
        flash('Invalid credentials.')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/add_member', methods=['GET', 'POST'])
@login_required
def add_member():
    if request.method == 'POST':
        member = FamilyMember(
            name=request.form['name'],
            phone=request.form.get('phone', ''),
            email=request.form.get('email', ''),
            relation=request.form['relation'],
            date_of_birth=datetime.strptime(request.form['date_of_birth'], '%Y-%m-%d').date() if request.form.get('date_of_birth') else None,
            medical_conditions=request.form.get('medical_conditions', ''),
            allergies=request.form.get('allergies', ''),
            emergency_contact=request.form.get('emergency_contact', ''),
            user_id=current_user.id
        )
        db.session.add(member)
        db.session.commit()
        flash(f'Family member {member.name} added successfully.')
        return redirect(url_for('home'))
    return render_template('add_member.html')

@app.route('/edit_member/<int:member_id>', methods=['GET', 'POST'])
@login_required
def edit_member(member_id):
    member = FamilyMember.query.filter_by(id=member_id, user_id=current_user.id).first_or_404()
    
    if request.method == 'POST':
        member.name = request.form['name']
        member.phone = request.form.get('phone', '')
        member.email = request.form.get('email', '')
        member.relation = request.form['relation']
        member.date_of_birth = datetime.strptime(request.form['date_of_birth'], '%Y-%m-%d').date() if request.form.get('date_of_birth') else None
        member.medical_conditions = request.form.get('medical_conditions', '')
        member.allergies = request.form.get('allergies', '')
        member.emergency_contact = request.form.get('emergency_contact', '')
        
        db.session.commit()
        flash(f'Family member {member.name} updated successfully.')
        return redirect(url_for('member_detail', member_id=member.id))
    
    return render_template('edit_member.html', member=member)

@app.route('/add_medication/<int:member_id>', methods=['GET', 'POST'])
@login_required
def add_medication(member_id):
    member = FamilyMember.query.filter_by(id=member_id, user_id=current_user.id).first_or_404()
    
    if request.method == 'POST':
        medication = Medication(
            name=request.form['name'],
            generic_name=request.form.get('generic_name', ''),
            dosage=request.form['dosage'],
            form=request.form['form'],
            instructions=request.form.get('instructions', ''),
            prescribing_doctor=request.form.get('prescribing_doctor', ''),
            prescription_date=datetime.strptime(request.form['prescription_date'], '%Y-%m-%d').date() if request.form.get('prescription_date') else None,
            start_date=datetime.strptime(request.form['start_date'], '%Y-%m-%d').date(),
            end_date=datetime.strptime(request.form['end_date'], '%Y-%m-%d').date() if request.form.get('end_date') else None,
            total_quantity=int(request.form['total_quantity']) if request.form.get('total_quantity') else None,
            remaining_quantity=int(request.form['remaining_quantity']) if request.form.get('remaining_quantity') else None,
            refill_reminder_threshold=int(request.form.get('refill_reminder_threshold', 5)),
            member_id=member_id
        )
        
        db.session.add(medication)
        db.session.flush()  # Get the medication ID
        
        # Add schedule
        schedule_times = request.form.getlist('schedule_time')
        frequency = request.form['frequency']
        frequency_details = request.form.get('frequency_details', '')
        meal_timing = request.form.get('meal_timing', '')
        
        for schedule_time in schedule_times:
            if schedule_time:
                schedule = MedicationSchedule(
                    time=datetime.strptime(schedule_time, '%H:%M').time(),
                    frequency=frequency,
                    frequency_details=frequency_details,
                    meal_timing=meal_timing,
                    medication_id=medication.id
                )
                db.session.add(schedule)
        
        db.session.commit()
        flash(f'Medication {medication.name} added successfully for {member.name}.')
        return redirect(url_for('member_detail', member_id=member_id))
    
    return render_template('add_medication.html', member=member)

@app.route('/mark_taken/<int:log_id>', methods=['POST'])
@login_required
def mark_taken(log_id):
    log = MedicationLog.query.join(FamilyMember).filter(
        MedicationLog.id == log_id,
        FamilyMember.user_id == current_user.id
    ).first_or_404()
    
    log.status = 'taken'
    log.taken_time = datetime.utcnow()
    log.notes = request.form.get('notes', '')
    log.side_effects = request.form.get('side_effects', '')
    
    # Update medication quantity if tracked
    medication = log.medication
    if medication.remaining_quantity is not None:
        medication.remaining_quantity = max(0, medication.remaining_quantity - 1)
    
    db.session.commit()
    flash('Medication marked as taken.')
    return redirect(url_for('home'))

@app.route('/mark_missed/<int:log_id>', methods=['POST'])
@login_required
def mark_missed(log_id):
    log = MedicationLog.query.join(FamilyMember).filter(
        MedicationLog.id == log_id,
        FamilyMember.user_id == current_user.id
    ).first_or_404()
    
    log.status = 'missed'
    log.notes = request.form.get('notes', '')
    
    db.session.commit()
    flash('Medication marked as missed.')
    return redirect(url_for('home'))

@app.route('/skip_dose/<int:log_id>', methods=['POST'])
@login_required
def skip_dose(log_id):
    log = MedicationLog.query.join(FamilyMember).filter(
        MedicationLog.id == log_id,
        FamilyMember.user_id == current_user.id
    ).first_or_404()
    
    log.status = 'skipped'
    log.notes = request.form.get('notes', '')
    
    db.session.commit()
    flash('Medication marked as skipped.')
    return redirect(url_for('home'))

# Legacy routes for backward compatibility
@app.route('/add_pill/<int:member_id>', methods=['POST'])
@login_required
def add_pill(member_id):
    pill = Pill(name=request.form['pill_name'], time=request.form['pill_time'], member_id=member_id)
    db.session.add(pill)
    db.session.commit()
    return redirect(url_for('home'))

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

@app.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    if request.method == 'POST':
        current_user.first_name = request.form['first_name']
        current_user.last_name = request.form['last_name']
        current_user.phone = request.form.get('phone', '')
        current_user.timezone = request.form.get('timezone', 'UTC')
        current_user.email_notifications = 'email_notifications' in request.form
        current_user.sms_notifications = 'sms_notifications' in request.form
        
        if request.form.get('new_password'):
            current_user.set_password(request.form['new_password'])
        
        db.session.commit()
        flash('Settings updated successfully.')
        return redirect(url_for('settings'))
    
    return render_template('settings.html')

@app.route('/reports')
@login_required
def reports():
    # Get adherence data for all family members
    members = FamilyMember.query.filter_by(user_id=current_user.id, is_active=True).all()
    
    # Calculate adherence for past 30 days
    thirty_days_ago = datetime.now() - timedelta(days=30)
    adherence_data = []
    
    for member in members:
        total_scheduled = MedicationLog.query.filter_by(member_id=member.id).filter(
            MedicationLog.scheduled_time >= thirty_days_ago
        ).count()
        
        taken_count = MedicationLog.query.filter_by(member_id=member.id, status='taken').filter(
            MedicationLog.scheduled_time >= thirty_days_ago
        ).count()
        
        missed_count = MedicationLog.query.filter_by(member_id=member.id, status='missed').filter(
            MedicationLog.scheduled_time >= thirty_days_ago
        ).count()
        
        adherence_rate = (taken_count / total_scheduled * 100) if total_scheduled > 0 else 0
        
        adherence_data.append({
            'member': member,
            'total_scheduled': total_scheduled,
            'taken_count': taken_count,
            'missed_count': missed_count,
            'adherence_rate': adherence_rate
        })
    
    return render_template('reports.html', adherence_data=adherence_data)

@app.route('/api/medication_log/<int:log_id>/status', methods=['POST'])
@login_required
def update_medication_status(log_id):
    """API endpoint for updating medication status via AJAX"""
    log = MedicationLog.query.join(FamilyMember).filter(
        MedicationLog.id == log_id,
        FamilyMember.user_id == current_user.id
    ).first_or_404()
    
    data = request.get_json()
    status = data.get('status')
    notes = data.get('notes', '')
    side_effects = data.get('side_effects', '')
    
    if status not in ['taken', 'missed', 'skipped']:
        return jsonify({'error': 'Invalid status'}), 400
    
    log.status = status
    log.notes = notes
    log.side_effects = side_effects
    
    if status == 'taken':
        log.taken_time = datetime.utcnow()
        # Update medication quantity if tracked
        medication = log.medication
        if medication.remaining_quantity is not None:
            medication.remaining_quantity = max(0, medication.remaining_quantity - 1)
    
    db.session.commit()
    
    return jsonify({
        'success': True,
        'message': f'Medication marked as {status}',
        'remaining_quantity': log.medication.remaining_quantity
    })

@app.route('/reset_request', methods=['GET', 'POST'])
def reset_request():
    if request.method == 'POST':
        user = User.query.filter_by(email=request.form['email']).first()
        if user:
            user.reset_token = os.urandom(8).hex()
            db.session.commit()
            reset_url = url_for('reset_password', token=user.reset_token, _external=True)
            
            try:
                mail.send(Message(
                    "Password Reset - PillPal", 
                    recipients=[user.email], 
                    body=f"Click here to reset your password: {reset_url}\n\nThis link will expire in 24 hours."
                ))
                flash('Reset link sent to your email.')
            except Exception as e:
                flash('Failed to send reset email. Please try again.')
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
        user.set_password(request.form['password'])
        user.reset_token = None
        db.session.commit()
        flash('Password updated successfully.')
        return redirect(url_for('login'))
    return render_template('reset_password.html')

# Enhanced notification system
def send_notification(user, member, medication, message, notification_type='reminder'):
    """Send notification via enabled channels"""
    results = []
    
    # Send email if enabled
    if user.email_notifications and user.email:
        try:
            mail.send(Message(
                f'PillPal - {notification_type.title()}',
                recipients=[user.email],
                body=message,
                html=render_template('emails/medication_reminder.html', 
                                   user=user, member=member, medication=medication, message=message)
            ))
            results.append(f"Email sent to {user.email}")
        except Exception as e:
            results.append(f"Email failed: {e}")
    
    # Send SMS if enabled and Twilio is configured
    if user.sms_notifications and twilio_client and member.phone:
        try:
            # Determine if using WhatsApp or regular SMS
            to_number = f"whatsapp:{member.phone}" if TWILIO_PHONE_NUMBER and TWILIO_PHONE_NUMBER.startswith("whatsapp:") else member.phone
            
            twilio_client.messages.create(
                to=to_number,
                from_=TWILIO_PHONE_NUMBER,
                body=message
            )
            results.append(f"SMS sent to {to_number}")
        except Exception as e:
            results.append(f"SMS failed: {e}")
    
    return results

scheduler = BackgroundScheduler()

@scheduler.scheduled_job('interval', minutes=1)
def send_medication_reminders():
    """Enhanced medication reminder system"""
    with app.app_context():
        now = datetime.now()
        current_time = now.strftime("%H:%M")
        
        print(f"[{now}] Checking for medication reminders...")
        
        # Find all pending medication logs for current time
        pending_logs = db.session.query(MedicationLog).join(MedicationSchedule).join(Medication).join(FamilyMember).filter(
            MedicationLog.status == 'pending',
            MedicationSchedule.time == datetime.strptime(current_time, "%H:%M").time(),
            Medication.is_active == True,
            MedicationSchedule.is_active == True,
            FamilyMember.is_active == True
        ).all()
        
        for log in pending_logs:
            member = log.patient
            medication = log.medication
            user = member.owner
            
            # Create reminder message
            meal_info = ""
            if log.schedule and log.schedule.meal_timing:
                meal_timing_map = {
                    'before_meal': 'before meals',
                    'with_meal': 'with meals', 
                    'after_meal': 'after meals',
                    'empty_stomach': 'on empty stomach'
                }
                meal_info = f" ({meal_timing_map.get(log.schedule.meal_timing, '')})"
            
            message = f"🔔 Medication Reminder\n\n" \
                     f"Patient: {member.name}\n" \
                     f"Medication: {medication.name} ({medication.dosage})\n" \
                     f"Time: {current_time}{meal_info}\n"
            
            if medication.instructions:
                message += f"Instructions: {medication.instructions}\n"
            
            if medication.remaining_quantity is not None:
                message += f"Remaining: {medication.remaining_quantity} doses\n"
            
            message += f"\nReply to confirm medication has been taken."
            
            # Send notification
            results = send_notification(user, member, medication, message, 'reminder')
            
            # Log notification attempt
            notification = Notification(
                user_id=user.id,
                member_id=member.id,
                medication_id=medication.id,
                notification_type='reminder',
                message=message,
                scheduled_time=log.scheduled_time,
                sent_time=now,
                delivery_method='both' if user.email_notifications and user.sms_notifications else ('email' if user.email_notifications else 'sms'),
                status='sent' if results else 'failed'
            )
            db.session.add(notification)
            
            print(f"[{now}] Reminder sent for {member.name} - {medication.name}: {results}")

@scheduler.scheduled_job('cron', hour=9, minute=0)  # Daily at 9 AM
def send_missed_medication_alerts():
    """Send alerts for missed medications from previous day"""
    with app.app_context():
        yesterday = datetime.now() - timedelta(days=1)
        yesterday_start = datetime.combine(yesterday.date(), dt_time.min)
        yesterday_end = datetime.combine(yesterday.date(), dt_time.max)
        
        missed_logs = MedicationLog.query.filter(
            MedicationLog.status == 'missed',
            MedicationLog.scheduled_time >= yesterday_start,
            MedicationLog.scheduled_time <= yesterday_end
        ).all()
        
        # Group by user
        user_missed = {}
        for log in missed_logs:
            user_id = log.patient.user_id
            if user_id not in user_missed:
                user_missed[user_id] = []
            user_missed[user_id].append(log)
        
        for user_id, logs in user_missed.items():
            user = User.query.get(user_id)
            if not user:
                continue
            
            message = f"⚠️ Missed Medication Alert\n\n"
            message += f"The following medications were missed yesterday:\n\n"
            
            for log in logs:
                message += f"• {log.patient.name}: {log.medication.name} at {log.scheduled_time.strftime('%H:%M')}\n"
            
            message += f"\nPlease ensure medications are taken as prescribed."
            
            # Send to first family member for notification purposes
            member = logs[0].patient
            send_notification(user, member, logs[0].medication, message, 'missed')
            
            print(f"Missed medication alert sent to {user.email}")

@scheduler.scheduled_job('cron', hour=18, minute=0)  # Daily at 6 PM
def send_refill_reminders():
    """Send reminders for medications running low"""
    with app.app_context():
        low_stock_medications = Medication.query.join(FamilyMember).filter(
            Medication.is_active == True,
            Medication.remaining_quantity.isnot(None),
            Medication.remaining_quantity <= Medication.refill_reminder_threshold,
            FamilyMember.is_active == True
        ).all()
        
        # Group by user
        user_refills = {}
        for medication in low_stock_medications:
            user_id = medication.patient.user_id
            if user_id not in user_refills:
                user_refills[user_id] = []
            user_refills[user_id].append(medication)
        
        for user_id, medications in user_refills.items():
            user = User.query.get(user_id)
            if not user:
                continue
            
            message = f"💊 Refill Reminder\n\n"
            message += f"The following medications are running low:\n\n"
            
            for medication in medications:
                message += f"• {medication.patient.name}: {medication.name}\n"
                message += f"  Remaining: {medication.remaining_quantity} doses\n"
                if medication.prescribing_doctor:
                    message += f"  Doctor: {medication.prescribing_doctor}\n"
                message += "\n"
            
            message += f"Please contact your healthcare provider for refills."
            
            # Send notification using first medication for member reference
            member = medications[0].patient
            send_notification(user, member, medications[0], message, 'refill')
            
            print(f"Refill reminder sent to {user.email}")

with app.app_context():
    db.create_all()

scheduler.start()

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)

