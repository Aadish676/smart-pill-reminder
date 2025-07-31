from flask import Flask, render_template, request, redirect, url_for, flash, session, send_from_directory, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, logout_user, login_required, current_user, UserMixin
from flask_mail import Mail, Message
from flask_migrate import Migrate
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime, timedelta
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
import os
from dotenv import load_dotenv
from twilio.rest import Client
import re
import secrets

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv("SECRET_KEY", "dev")
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///pillpal.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

UPLOAD_FOLDER = os.path.join(os.getcwd(), 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Email configuration with better error handling
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = os.getenv("MAIL_USERNAME")
app.config['MAIL_PASSWORD'] = os.getenv("MAIL_PASSWORD")

# Initialize mail only if credentials are provided
mail = None
if app.config['MAIL_USERNAME'] and app.config['MAIL_PASSWORD']:
    mail = Mail(app)
    print("Email service initialized successfully")
else:
    print("Warning: Email credentials not found. Email notifications will be disabled.")

# Twilio configuration with better error handling
TWILIO_SID = os.getenv("TWILIO_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH")
TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE")

twilio_client = None
if TWILIO_SID and TWILIO_AUTH_TOKEN and TWILIO_PHONE_NUMBER:
    try:
        twilio_client = Client(TWILIO_SID, TWILIO_AUTH_TOKEN)
        print("Twilio service initialized successfully")
    except Exception as e:
        print(f"Warning: Failed to initialize Twilio client: {e}")
        twilio_client = None
else:
    print("Warning: Twilio credentials not found. SMS/WhatsApp notifications will be disabled.")

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
migrate = Migrate(app, db)

# Helper function to validate phone numbers
def validate_phone(phone):
    # Remove all non-digit characters except +
    cleaned = re.sub(r'[^\d+]', '', phone)
    # Check if it's a valid format (at least 10 digits, optionally starting with +)
    if re.match(r'^\+?\d{10,15}$', cleaned):
        return cleaned
    return None

# Helper function to validate email
def validate_email(email):
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)  # Increased length for hashed passwords
    reset_token = db.Column(db.String(255), nullable=True)
    reset_token_expiry = db.Column(db.DateTime, nullable=True)  # Token expiry time
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime, nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    family_members = db.relationship('FamilyMember', backref='owner', lazy=True)
    
    def set_password(self, password):
        """Set password hash"""
        self.password = generate_password_hash(password)
    
    def check_password(self, password):
        """Check password hash"""
        return check_password_hash(self.password, password)
    
    def generate_reset_token(self):
        """Generate a reset token with expiry"""
        self.reset_token = secrets.token_hex(32)
        self.reset_token_expiry = datetime.utcnow() + timedelta(hours=1)  # 1 hour expiry
        db.session.commit()
        return self.reset_token
    
    def verify_reset_token(self, token):
        """Verify reset token and check expiry"""
        if (self.reset_token == token and 
            self.reset_token_expiry and 
            datetime.utcnow() < self.reset_token_expiry):
            return True
        return False

class FamilyMember(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    phone = db.Column(db.String(20))
    email = db.Column(db.String(120), nullable=True)  # Patient's Gmail ID for direct notifications
    relation = db.Column(db.String(100))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    pills = db.relationship('Pill', backref='member', lazy=True)

class Pill(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    time = db.Column(db.String(10))
    status = db.Column(db.String(20), default='pending')
    member_id = db.Column(db.Integer, db.ForeignKey('family_member.id'), nullable=False)

class NotificationLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    pill_id = db.Column(db.Integer, db.ForeignKey('pill.id'), nullable=False)
    notification_type = db.Column(db.String(20))  # 'email' or 'sms'
    status = db.Column(db.String(20))  # 'sent', 'failed'
    error_message = db.Column(db.Text)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@app.route('/')
@login_required
def home():
    members = FamilyMember.query.filter_by(user_id=current_user.id).all()
    
    # Get notification service status
    email_enabled = mail is not None
    sms_enabled = twilio_client is not None
    
    return render_template('dashboard.html', 
                         members=members, 
                         email_enabled=email_enabled, 
                         sms_enabled=sms_enabled)

@app.route('/test_notification')
@login_required
def test_notification():
    now = datetime.now().strftime("%H:%M:%S")
    member = FamilyMember.query.filter_by(user_id=current_user.id).first()
    if not member:
        flash("No family member found for test. Please add a family member first.", "error")
        return redirect(url_for('home'))

    msg_body = f"[{now}] Test notification for {member.name} - your pill reminder system is working!"
    results = []

    # Test email notification
    if mail:
        email_recipients = []
        if current_user.email:
            email_recipients.append(current_user.email)
        if member.email and member.email != current_user.email:
            email_recipients.append(member.email)
            
        if email_recipients:
            try:
                current_date = datetime.now().strftime("%A, %B %d, %Y at %I:%M %p")
                
                # Create beautiful HTML email for test
                html_content = render_template('email/pill_reminder.html',
                    patient_name=member.name,
                    patient_phone=member.phone,
                    patient_email=member.email,
                    pill_name="Test Medication",
                    pill_time=now,
                    current_date=current_date,
                    recipient_email=', '.join(email_recipients)
                )
                
                msg = Message(
                    subject=f'🧪 Test Medication Reminder: {member.name}',
                    recipients=email_recipients,
                    html=html_content,
                    body=msg_body
                )
                mail.send(msg)
                recipients_str = ', '.join(email_recipients)
                results.append(f"✓ Beautiful HTML email sent successfully to {recipients_str}")
            except Exception as e:
                results.append(f"✗ Email failed: {str(e)}")
        else:
            results.append("✗ No email addresses found (neither account owner nor patient has email)")
    else:
        results.append("✗ Email service not configured (missing credentials)")

    # Test SMS/WhatsApp notification
    if twilio_client and member.phone:
        try:
            # Validate and format phone number
            validated_phone = validate_phone(member.phone)
            if not validated_phone:
                results.append(f"✗ Invalid phone number format: {member.phone}")
            else:
                to_number = f"whatsapp:{validated_phone}" if TWILIO_PHONE_NUMBER.startswith("whatsapp:") else validated_phone
                message = twilio_client.messages.create(
                    to=to_number, 
                    from_=TWILIO_PHONE_NUMBER, 
                    body=msg_body
                )
                results.append(f"✓ SMS/WhatsApp sent successfully to {to_number}")
        except Exception as e:
            results.append(f"✗ SMS/WhatsApp failed: {str(e)}")
    else:
        if not twilio_client:
            results.append("✗ SMS service not configured (missing Twilio credentials)")
        else:
            results.append(f"✗ No phone number found for {member.name}")

    # Flash results to user
    for result in results:
        if "✓" in result:
            flash(result, "success")
        else:
            flash(result, "error")
    
    return redirect(url_for('home'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form['email'].strip().lower()
        password = request.form['password']
        
        # Validate email format
        if not validate_email(email):
            flash('Please enter a valid email address.', 'error')
            return redirect(url_for('register'))
            
        if User.query.filter_by(email=email).first():
            flash('Email already registered.', 'error')
            return redirect(url_for('register'))
            
        if len(password) < 8:
            flash('Password must be at least 8 characters long.', 'error')
            return redirect(url_for('register'))
            
        # Check password strength
        if not re.search(r'[A-Z]', password):
            flash('Password must contain at least one uppercase letter.', 'error')
            return redirect(url_for('register'))
        if not re.search(r'[0-9]', password):
            flash('Password must contain at least one number.', 'error')
            return redirect(url_for('register'))
            
        user = User(email=email)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        flash('Account created successfully! You can now log in.', 'success')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email'].strip().lower()
        password = request.form['password']
        
        user = User.query.filter_by(email=email).first()
        if user and user.is_active and user.check_password(password):
            user.last_login = datetime.utcnow()
            db.session.commit()
            login_user(user)
            flash(f'Welcome back! Logged in successfully.', 'success')
            return redirect(url_for('home'))
        else:
            flash('Invalid email or password. Please try again.', 'error')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/add_member', methods=['POST'])
@login_required
def add_member():
    name = request.form['name'].strip()
    phone = request.form['phone'].strip()
    email = request.form.get('email', '').strip()
    relation = request.form['relation'].strip()
    
    # Validate inputs
    if not name:
        flash('Name is required.', 'error')
        return redirect(url_for('home'))
        
    if not phone:
        flash('Phone number is required.', 'error')
        return redirect(url_for('home'))
        
    # Validate and format phone number
    validated_phone = validate_phone(phone)
    if not validated_phone:
        flash('Please enter a valid phone number (at least 10 digits).', 'error')
        return redirect(url_for('home'))
        
    # Validate email if provided
    if email and not validate_email(email):
        flash('Please enter a valid email address for the patient.', 'error')
        return redirect(url_for('home'))
        
    if not relation:
        flash('Relation is required.', 'error')
        return redirect(url_for('home'))
    
    member = FamilyMember(
        name=name, 
        phone=validated_phone, 
        email=email if email else None,
        relation=relation, 
        user_id=current_user.id
    )
    db.session.add(member)
    db.session.commit()
    flash(f'Family member {name} added successfully.', 'success')
    return redirect(url_for('home'))

@app.route('/add_pill/<int:member_id>', methods=['POST'])
@login_required
def add_pill(member_id):
    pill_name = request.form['pill_name'].strip()
    pill_time = request.form['pill_time'].strip()
    
    # Validate inputs
    if not pill_name:
        flash('Pill name is required.', 'error')
        return redirect(url_for('home'))
        
    if not pill_time:
        flash('Pill time is required.', 'error')
        return redirect(url_for('home'))
    
    # Verify member belongs to current user
    member = FamilyMember.query.filter_by(id=member_id, user_id=current_user.id).first()
    if not member:
        flash('Invalid family member.', 'error')
        return redirect(url_for('home'))
    
    pill = Pill(name=pill_name, time=pill_time, member_id=member_id)
    db.session.add(pill)
    db.session.commit()
    flash(f'Pill {pill_name} added for {member.name} at {pill_time}.', 'success')
    return redirect(url_for('home'))

@app.route('/reset_pills')
@login_required
def reset_pills():
    """Reset all pills to pending status for testing"""
    try:
        # Get all pills for current user's family members
        member_ids = [m.id for m in FamilyMember.query.filter_by(user_id=current_user.id).all()]
        pills = Pill.query.filter(Pill.member_id.in_(member_ids)).all()
        
        count = 0
        for pill in pills:
            if pill.status != 'pending':
                pill.status = 'pending'
                count += 1
        
        db.session.commit()
        flash(f'Reset {count} pills to pending status.', 'success')
    except Exception as e:
        flash(f'Error resetting pills: {str(e)}', 'error')
    
    return redirect(url_for('home'))

@app.route('/notification_logs')
@login_required
def notification_logs():
    """View notification logs for current user"""
    # Get all pills for current user's family members
    member_ids = [m.id for m in FamilyMember.query.filter_by(user_id=current_user.id).all()]
    pills = Pill.query.filter(Pill.member_id.in_(member_ids)).all()
    pill_ids = [p.id for p in pills]
    
    logs = NotificationLog.query.filter(NotificationLog.pill_id.in_(pill_ids)).order_by(NotificationLog.timestamp.desc()).limit(50).all()
    
    # Get notification service status
    email_enabled = mail is not None
    sms_enabled = twilio_client is not None
    
    return render_template('notification_logs.html', 
                         logs=logs, 
                         pills={p.id: p for p in pills},
                         email_enabled=email_enabled,
                         sms_enabled=sms_enabled)

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
        email = request.form['email'].strip().lower()
        user = User.query.filter_by(email=email).first()
        if user and user.is_active:
            if mail:
                token = user.generate_reset_token()
                reset_url = url_for('reset_password', token=token, _external=True)
                
                # Send HTML email
                msg = Message(
                    "Password Reset Request - Smart Pill Reminder",
                    recipients=[user.email],
                    html=render_template('email/password_reset.html', 
                                       user=user, reset_url=reset_url),
                    body=f"Click here to reset your password: {reset_url}"
                )
                mail.send(msg)
                flash('Password reset instructions have been sent to your email.', 'success')
            else:
                flash('Email service is not configured. Please contact support.', 'error')
        else:
            # Don't reveal if email exists or not for security
            flash('If that email exists in our system, you will receive reset instructions.', 'info')
        return redirect(url_for('login'))
    return render_template('reset_request.html')

@app.route('/reset_password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    user = User.query.filter_by(reset_token=token).first()
    if not user or not user.verify_reset_token(token):
        flash('Invalid or expired password reset token.', 'error')
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        password = request.form['password']
        confirm_password = request.form['confirm_password']
        
        if password != confirm_password:
            flash('Passwords do not match.', 'error')
            return render_template('reset_password.html', token=token)
            
        if len(password) < 8:
            flash('Password must be at least 8 characters long.', 'error')
            return render_template('reset_password.html', token=token)
            
        user.set_password(password)
        user.reset_token = None
        user.reset_token_expiry = None
        db.session.commit()
        flash('Your password has been updated successfully!', 'success')
        return redirect(url_for('login'))
    return render_template('reset_password.html', token=token)

scheduler = BackgroundScheduler()

def log_notification(pill_id, notification_type, status, error_message=None):
    """Log notification attempt to database"""
    try:
        log_entry = NotificationLog(
            pill_id=pill_id,
            notification_type=notification_type,
            status=status,
            error_message=error_message
        )
        db.session.add(log_entry)
        db.session.commit()
    except Exception as e:
        print(f"Failed to log notification: {e}")

@scheduler.scheduled_job('interval', seconds=60)
def send_reminders():
    with app.app_context():
        now = datetime.now().strftime("%H:%M")
        print(f"[{now}] Scheduler checking for due pills...")
        
        # Find pills due at current time
        due_pills = Pill.query.filter_by(time=now, status='pending').all()
        if not due_pills:
            print(f"[{now}] No pills due at this time.")
            return
            
        print(f"[{now}] Found {len(due_pills)} pills due for reminders")
        
        for pill in due_pills:
            member = pill.member
            user = member.owner
            msg_body = f"💊 Pill Reminder: {member.name} should take {pill.name} now at {now}."
            
            notifications_sent = False

            # Send email notification
            if mail:
                email_recipients = []
                if user.email:
                    email_recipients.append(user.email)
                if member.email and member.email != user.email:
                    email_recipients.append(member.email)
                    
                if email_recipients:
                    try:
                        current_date = datetime.now().strftime("%A, %B %d, %Y at %I:%M %p")
                        
                        # Create beautiful HTML email
                        html_content = render_template('email/pill_reminder.html',
                            patient_name=member.name,
                            patient_phone=member.phone,
                            patient_email=member.email,
                            pill_name=pill.name,
                            pill_time=pill.time,
                            current_date=current_date,
                            recipient_email=', '.join(email_recipients)
                        )
                        
                        msg = Message(
                            subject=f'💊 Medication Reminder: {pill.name} for {member.name}',
                            recipients=email_recipients,
                            html=html_content,
                            body=msg_body  # Fallback plain text
                        )
                        mail.send(msg)
                        recipients_str = ', '.join(email_recipients)
                        print(f"[{now}] Beautiful HTML email sent to {recipients_str} for {pill.name}")
                        log_notification(pill.id, 'email', 'sent')
                        notifications_sent = True
                    except Exception as e:
                        error_msg = str(e)
                        recipients_str = ', '.join(email_recipients)
                        print(f"[{now}] Email failed for {recipients_str}: {error_msg}")
                        log_notification(pill.id, 'email', 'failed', error_msg)

            # Send SMS/WhatsApp notification
            if twilio_client and member.phone:
                try:
                    # Validate phone number
                    validated_phone = validate_phone(member.phone)
                    if validated_phone:
                        to_number = f"whatsapp:{validated_phone}" if TWILIO_PHONE_NUMBER and TWILIO_PHONE_NUMBER.startswith("whatsapp:") else validated_phone
                        message = twilio_client.messages.create(
                            to=to_number,
                            from_=TWILIO_PHONE_NUMBER,
                            body=msg_body
                        )
                        print(f"[{now}] SMS/WhatsApp sent to {to_number} for {pill.name}")
                        log_notification(pill.id, 'sms', 'sent')
                        notifications_sent = True
                    else:
                        error_msg = f"Invalid phone number format: {member.phone}"
                        print(f"[{now}] {error_msg}")
                        log_notification(pill.id, 'sms', 'failed', error_msg)
                except Exception as e:
                    error_msg = str(e)
                    print(f"[{now}] SMS/WhatsApp failed to {member.phone}: {error_msg}")
                    log_notification(pill.id, 'sms', 'failed', error_msg)

            # Update pill status
            try:
                if notifications_sent:
                    pill.status = 'notified'
                else:
                    pill.status = 'failed'
                    print(f"[{now}] No notifications sent for {pill.name} - marking as failed")
                db.session.commit()
                print(f"[{now}] Updated status for {pill.name} to {pill.status}")
            except Exception as e:
                print(f"[{now}] Error updating status for {pill.name}: {e}")
                # Try to rollback
                try:
                    db.session.rollback()
                except:
                    pass

with app.app_context():
    db.create_all()

scheduler.start()

if __name__ == '__main__':
    app.run(debug=True)

