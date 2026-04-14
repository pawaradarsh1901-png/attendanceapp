from flask import Flask, request, jsonify, render_template, session, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from datetime import datetime, date
import uuid
import os
import pytz

IST = pytz.timezone('Asia/Kolkata')

app = Flask(__name__)
CORS(app)
app.secret_key = os.environ.get('SECRET_KEY', 'default-secret-key-12345')

# Admin Credentials (In production, use environment variables)
ADMIN_EMAIL = os.environ.get('ADMIN_EMAIL', 'admin@example.com')
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'admin123')

# Database Configuration
# Use DATABASE_URL for deployment (e.g. PostgreSQL on Heroku/Railway) 
# or local SQLite for development
db_url = os.environ.get('DATABASE_URL')
if db_url and db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = db_url or 'sqlite:///attendance.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key')

db = SQLAlchemy(app)

# --- Models ---

class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    emp_id = db.Column(db.String(50), unique=True, nullable=False)
    qr_token = db.Column(db.String(100), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(IST))
    attendances = db.relationship('Attendance', backref='user', lazy=True, cascade="all, delete-orphan")

class Attendance(db.Model):
    __tablename__ = 'attendance'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    date = db.Column(db.Date, nullable=False, default=date.today)
    in_time = db.Column(db.String(20))
    out_time = db.Column(db.String(20))

# --- Database Initialization ---

with app.app_context():
    db.create_all()

# --- Routes ---

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/admin')
def admin():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    return render_template('admin.html')

@app.route('/login')
def login():
    if session.get('logged_in'):
        return redirect(url_for('admin'))
    return render_template('login.html')

@app.route('/api/login', methods=['POST'])
def api_login():
    data = request.json
    email = data.get('email')
    password = data.get('password')
    
    if email == ADMIN_EMAIL and password == ADMIN_PASSWORD:
        session['logged_in'] = True
        return jsonify({'success': True})
    else:
        return jsonify({'error': 'Invalid email or password'}), 401

@app.route('/logout')
@app.route('/api/logout')
def api_logout():
    session.pop('logged_in', None)
    return redirect(url_for('login'))

@app.route('/api/mark_attendance', methods=['POST'])
def mark_attendance():
    content = request.json
    qr_token = content.get('qr_token')
    
    if not qr_token:
        return jsonify({'error': 'Missing QR token'}), 400
    
    user = User.query.filter_by(qr_token=qr_token).first()
    if not user:
        return jsonify({'error': 'Student not found!'}), 404
    
    now_ist = datetime.now(IST)
    today = now_ist.date()
    now_time = now_ist.strftime("%H:%M:%S")
    
    # Check for existing log for today
    log = Attendance.query.filter_by(user_id=user.id, date=today).first()
    
    if not log:
        # First scan of the day: Mark IN
        new_log = Attendance(user_id=user.id, date=today, in_time=now_time)
        db.session.add(new_log)
        db.session.commit()
        return jsonify({
            'status': 'IN',
            'user': user.name,
            'message': f"Welcome, {user.name}!",
            'time': now_time
        })
    elif log.in_time and not log.out_time:
        # Second scan: Mark OUT
        log.out_time = now_time
        db.session.commit()
        return jsonify({
            'status': 'OUT',
            'user': user.name,
            'message': f"Goodbye, {user.name}!",
            'time': now_time
        })
    else:
        # Already marked both
        return jsonify({
            'error': f"{user.name} has already marked attendance for today.",
            'user': user.name
        }), 400

@app.route('/api/attendance', methods=['GET'])
def get_attendance():
    date_filter = request.args.get('date', 'today')
    
    query = Attendance.query
    if date_filter == 'today':
        today = datetime.now(IST).date()
        query = query.filter_by(date=today)
    
    logs = query.order_by(Attendance.date.desc(), Attendance.in_time.desc()).all()
    
    results = []
    for log in logs:
        results.append({
            'id': log.id,
            'date': log.date.strftime("%Y-%m-%d"),
            'user_id': log.user_id,
            'name': log.user.name,
            'emp_id': log.user.emp_id,
            'in_time': log.in_time,
            'out_time': log.out_time
        })
    
    return jsonify(results)

@app.route('/api/users', methods=['GET', 'POST'])
def handle_users():
    if request.method == 'POST':
        data = request.json
        name = data.get('name')
        emp_id = data.get('emp_id')
        
        if not name or not emp_id:
            return jsonify({'error': 'Name and Emp ID are required'}), 400
            
        if User.query.filter_by(emp_id=emp_id).first():
            return jsonify({'error': 'Emp ID already exists'}), 400
            
        qr_token = str(uuid.uuid4())
        new_user = User(name=name, emp_id=emp_id, qr_token=qr_token)
        db.session.add(new_user)
        db.session.commit()
        
        return jsonify({
            'id': new_user.id,
            'name': new_user.name,
            'emp_id': new_user.emp_id,
            'qr_token': new_user.qr_token
        })
    
    users = User.query.order_by(User.created_at.desc()).all()
    return jsonify([{
        'id': u.id,
        'name': u.name,
        'emp_id': u.emp_id,
        'qr_token': u.qr_token,
        'created_at': u.created_at.isoformat()
    } for u in users])

@app.route('/api/users/<int:user_id>', methods=['GET'])
def get_user_details(user_id):
    user = User.query.get_or_404(user_id)
    history = Attendance.query.filter_by(user_id=user.id).order_by(Attendance.date.desc()).all()
    
    return jsonify({
        'user': {
            'id': user.id,
            'name': user.name,
            'emp_id': user.emp_id,
            'created_at': user.created_at.isoformat()
        },
        'history': [{
            'date': h.date.strftime("%Y-%m-%d"),
            'in_time': h.in_time,
            'out_time': h.out_time
        } for h in history]
    })

@app.route('/api/backup/db')
def backup_db():
    # Only allow logged in admins
    if not session.get('logged_in'):
        return jsonify({'error': 'Unauthorized'}), 401
    
    # Get the db path from config
    db_path = app.config['SQLALCHEMY_DATABASE_URI']
    if db_path.startswith('sqlite:///'):
        db_path = db_path.replace('sqlite:///', '')
        if os.path.exists(db_path):
            from flask import send_file
            return send_file(db_path, as_attachment=True, download_name=f'attendance_backup_{date.today()}.db')
    
    return jsonify({'error': 'Backup only supported for SQLite local database or file not found'}), 404

@app.route('/api/backup/csv')
def export_csv():
    if not session.get('logged_in'):
        return jsonify({'error': 'Unauthorized'}), 401
        
    import csv
    from io import BytesIO, StringIO
    from flask import send_file
    
    logs = Attendance.query.order_by(Attendance.date.desc(), Attendance.in_time.desc()).all()
    
    si = StringIO()
    cw = csv.writer(si)
    cw.writerow(['Date', 'Name', 'Student ID', 'In Time', 'Out Time'])
    for log in logs:
        cw.writerow([log.date.strftime("%Y-%m-%d"), log.user.name, log.user.emp_id, log.in_time, log.out_time])
    
    output = BytesIO()
    output.write(si.getvalue().encode('utf-8'))
    output.seek(0)
    
    return send_file(
        output,
        mimetype='text/csv',
        as_attachment=True,
        download_name=f'attendance_export_{date.today()}.csv'
    )

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
