# PillPal - Smart Medication Reminder System

A comprehensive family medication management system with multi-channel alerts (email & SMS), adherence tracking, and detailed reporting.

## 🌟 Features

### 👨‍👩‍👧‍👦 Family Management
- **Multi-patient support**: Manage medications for entire family
- **Detailed profiles**: Track medical conditions, allergies, emergency contacts
- **Role-based relationships**: Parent, child, spouse, etc.

### 💊 Medication Management
- **Comprehensive tracking**: Dosage, form, prescribing doctor, quantities
- **Flexible scheduling**: Daily, weekly, monthly, or as-needed
- **Meal timing**: Before/with/after meals, empty stomach
- **Refill alerts**: Automatic low-stock notifications

### 🔔 Smart Notifications
- **Multi-channel alerts**: Email and SMS/WhatsApp support
- **Real-time reminders**: Minute-by-minute medication alerts
- **Missed dose alerts**: Daily summary of missed medications
- **Refill reminders**: Low stock notifications

### 📊 Analytics & Reporting
- **Adherence tracking**: Calculate compliance rates over time
- **Visual dashboards**: Progress bars and status indicators
- **Performance reports**: Family-wide medication statistics
- **Recommendations**: Automated suggestions for improving adherence

### 🔒 Security & Privacy
- **Secure authentication**: Password hashing and session management
- **Data privacy**: All medical data stored securely
- **Password recovery**: Email-based reset functionality

## 🚀 Quick Start

### Prerequisites
- Python 3.8 or higher
- Email account (Gmail recommended)
- Optional: Twilio account for SMS notifications

### Installation

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd pillpal
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Environment Setup**
   ```bash
   cp .env.example .env
   # Edit .env with your configuration
   ```

4. **Database Setup**
   ```bash
   python -c "from app import app, db; app.app_context().push(); db.create_all()"
   ```

5. **Run the application**
   ```bash
   python app.py
   ```

6. **Access the application**
   Open your browser to `http://localhost:5000`

## ⚙️ Configuration

### Email Setup (Required)

For Gmail:
1. Enable 2-factor authentication
2. Generate an app password
3. Update `.env`:
   ```
   MAIL_USERNAME=your-email@gmail.com
   MAIL_PASSWORD=your-app-password
   ```

### SMS Setup (Optional)

For Twilio:
1. Create account at [twilio.com](https://twilio.com)
2. Get Account SID, Auth Token, and Phone Number
3. Update `.env`:
   ```
   TWILIO_SID=your-account-sid
   TWILIO_AUTH=your-auth-token
   TWILIO_PHONE=+1234567890
   ```

For WhatsApp:
```
TWILIO_PHONE=whatsapp:+1234567890
```

## 📱 Usage Guide

### Getting Started
1. **Register** your account with name, email, and phone
2. **Add family members** with their profiles and contact info
3. **Add medications** with schedules and dosage information
4. **Configure notifications** in Settings

### Daily Use
- **Dashboard**: View today's medications and quick stats
- **Mark medications**: Taken, missed, or skipped with one click
- **Receive alerts**: Email and SMS reminders at scheduled times
- **Track adherence**: Monitor compliance rates and patterns

### Advanced Features
- **Reports**: View 30-day adherence analytics
- **Member profiles**: Detailed medication history per person
- **Bulk actions**: Manage multiple medications efficiently
- **Export data**: Generate reports for healthcare providers

## 🏗️ Architecture

### Backend
- **Framework**: Flask with SQLAlchemy ORM
- **Database**: SQLite (easily upgradeable to PostgreSQL)
- **Authentication**: Flask-Login with secure password hashing
- **Scheduling**: APScheduler for automated reminders

### Frontend
- **UI Framework**: Bootstrap 5 with custom CSS
- **Icons**: Bootstrap Icons
- **Responsive**: Mobile-first design
- **Interactive**: AJAX for real-time updates

### Notifications
- **Email**: Flask-Mail with SMTP support
- **SMS**: Twilio integration
- **WhatsApp**: Twilio WhatsApp Business API
- **Scheduling**: Background jobs for automated alerts

## 📊 Database Schema

### Core Models
- **User**: Account management and preferences
- **FamilyMember**: Patient profiles and relationships
- **Medication**: Drug information and prescription details
- **MedicationSchedule**: Timing and frequency rules
- **MedicationLog**: Adherence tracking and history
- **Notification**: Alert delivery tracking

## 🔧 Development

### Project Structure
```
pillpal/
├── app.py                 # Main application
├── requirements.txt       # Dependencies
├── .env.example          # Environment template
├── templates/            # HTML templates
│   ├── base.html         # Base layout
│   ├── dashboard.html    # Main dashboard
│   ├── add_member.html   # Family member form
│   ├── add_medication.html # Medication form
│   └── ...              # Other templates
├── static/              # Static assets
│   └── style.css        # Custom styles
├── uploads/             # File uploads
└── migrations/          # Database migrations
```

### Adding Features
1. **New routes**: Add to `app.py`
2. **Database changes**: Update models and migrate
3. **Templates**: Create/modify HTML files
4. **Styles**: Update `static/style.css`

### Testing
```bash
# Test email notifications
curl http://localhost:5000/test_notification

# Check database
python -c "from app import *; print(User.query.all())"
```

## 📋 Requirements

### Python Packages
- Flask: Web framework
- Flask-SQLAlchemy: Database ORM
- Flask-Login: Authentication
- Flask-Mail: Email support
- Flask-Migrate: Database migrations
- APScheduler: Background scheduling
- Twilio: SMS/WhatsApp notifications
- python-dotenv: Environment management

### External Services
- **Email provider** (Gmail, Outlook, etc.)
- **Twilio account** (optional, for SMS)
- **Web hosting** (for production deployment)

## 🚀 Deployment

### Local Development
```bash
python app.py
```

### Production (Heroku example)
1. Create `Procfile`:
   ```
   web: gunicorn app:app
   ```

2. Set environment variables in hosting platform

3. Configure production database (PostgreSQL recommended)

### Docker Deployment
```dockerfile
FROM python:3.9
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
CMD ["gunicorn", "app:app", "--bind", "0.0.0.0:5000"]
```

## 🛠️ Troubleshooting

### Common Issues

**Email not sending:**
- Check email credentials
- Verify app password (not regular password)
- Ensure SMTP settings are correct

**SMS not working:**
- Verify Twilio credentials
- Check phone number format (+1234567890)
- Ensure sufficient Twilio balance

**Database errors:**
- Run database migration
- Check file permissions
- Verify SQLite file location

**Scheduler not running:**
- Check console for error messages
- Verify timezone settings
- Restart application

## 📝 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🤝 Contributing

1. Fork the repository
2. Create feature branch: `git checkout -b feature/new-feature`
3. Commit changes: `git commit -am 'Add new feature'`
4. Push to branch: `git push origin feature/new-feature`
5. Submit pull request

## 📞 Support

For support, email support@pillpal.com or create an issue in the GitHub repository.

## 🎯 Roadmap

- [ ] Mobile app (React Native)
- [ ] Voice reminders (Twilio Voice)
- [ ] Prescription OCR scanning
- [ ] Integration with pharmacy APIs
- [ ] Wearable device support
- [ ] Caregiver portal
- [ ] Multi-language support
- [ ] Advanced analytics and insights