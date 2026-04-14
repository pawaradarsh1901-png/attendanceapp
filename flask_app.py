from flask import Flask, request, jsonify, render_template, send_file, session, redirect, url_for
import functools
import sqlite3
import datetime
import uuid
import os
import qrcode
from io import BytesIO
import logging
import pytz

IST = pytz.timezone('Asia/Kolkata')


app = Flask(__name__)
app.secret_key = 'secure_attendance_key_123'  # Needed for session management
DATABASE = 'attendance.db'

# Hardcoded Admin Credentials
ADMIN_USER = 'admin'
ADMIN_PASS = 'admin'



def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            emp_id TEXT NOT NULL UNIQUE,
            qr_token TEXT NOT NULL UNIQUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            in_time TEXT,
            out_time TEXT,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    conn.commit()
    conn.close()

def migrate_db():
    # Cleanup: phone column was deprecated
    pass

# Initialize the db on startup
init_db()
migrate_db()

# --- Authentication Middleware ---
def login_required(f):
    @functools.wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session:
            # If it's an API route, send JSON 401
            if request.path.startswith('/api/'):
                return jsonify({'error': 'Unauthorized'}), 401
            # Otherwise redirect to login
            return redirect(url_for('login_page'))
        return f(*args, **kwargs)
    return decorated_function

# --- Frontend Routes ---
@app.route('/')
def scanner_panel():
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login_page():
    if request.method == 'POST':
        data = request.json
        if not data:
            data = request.form
        username = data.get('username')
        password = data.get('password')

        if username == ADMIN_USER and password == ADMIN_PASS:
            session['logged_in'] = True
            return jsonify({'success': True})
        else:
            return jsonify({'error': 'Invalid credentials'}), 401

    if 'logged_in' in session:
        return redirect(url_for('admin_panel'))
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('login_page'))

@app.route('/admin')
@login_required
def admin_panel():
    return render_template('admin.html')

# --- API Endpoints ---
@app.route('/api/users', methods=['GET'])
@login_required
def get_users():
    conn = get_db()
    users = conn.execute('SELECT * FROM users ORDER BY created_at DESC').fetchall()
    conn.close()
    return jsonify([dict(u) for u in users])

@app.route('/api/users', methods=['POST'])
@login_required
def create_user():
    data = request.json
    name = data.get('name')
    emp_id = data.get('emp_id')
    
    if not name:
        return jsonify({'error': 'Name is required'}), 400
    
    conn = get_db()
    
    # Auto-generate Student ID if not provided
    if not emp_id or emp_id.strip() == "":
        last_id_row = conn.execute('SELECT MAX(id) as last_id FROM users').fetchone()
        next_val = (last_id_row['last_id'] or 0) + 1
        emp_id = f"STU-{next_val:04d}" # e.g., STU-0001
    
    qr_token = str(uuid.uuid4())
    created_at = datetime.datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")
    try:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO users (name, emp_id, qr_token, created_at) VALUES (?, ?, ?, ?)", (name, emp_id, qr_token, created_at))
        conn.commit()
        new_id = cursor.lastrowid
        conn.close()
        return jsonify({'id': new_id, 'name': name, 'emp_id': emp_id, 'qr_token': qr_token, 'created_at': created_at}), 201
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({'error': 'Roll No / Student ID already exists'}), 400

@app.route('/api/users/<int:user_id>', methods=['DELETE'])
@login_required
def delete_user(user_id):
    conn = get_db()
    try:
        conn.execute('DELETE FROM attendance WHERE user_id = ?', (user_id,))
        conn.execute('DELETE FROM users WHERE id = ?', (user_id,))
        conn.commit()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()

@app.route('/api/qr/<qr_token>')
def generate_qr(qr_token):
    img = qrcode.make(qr_token)
    buf = BytesIO()
    img.save(buf)
    buf.seek(0)
    return send_file(buf, mimetype='image/png')

@app.route('/api/scan', methods=['POST'])
def scan_qr():
    # Public endpoint allowing the kiosk scanner to submit data
    data = request.json
    qr_token = data.get('qr_token')
    if not qr_token:
        return jsonify({'error': 'QR Token required'}), 400

    conn = get_db()
    user = conn.execute('SELECT * FROM users WHERE qr_token = ?', (qr_token,)).fetchone()
    
    if not user:
        conn.close()
        return jsonify({'error': 'Invalid QR Code / User Not Found'}), 404

    user_id = user['id']
    display_name = user['name']
    
    now_ist = datetime.datetime.now(IST)
    today = now_ist.date().isoformat()
    now_time = now_ist.strftime("%H:%M:%S")

    # Check for the latest open session (In but no Out)
    att = conn.execute('''
        SELECT * FROM attendance 
        WHERE user_id = ? 
        AND out_time IS NULL 
        ORDER BY id DESC LIMIT 1
    ''', (user_id,)).fetchone()

    status = ""
    if not att:
        # No open session -> Register a new "IN"
        conn.execute('INSERT INTO attendance (user_id, date, in_time) VALUES (?, ?, ?)', (user_id, today, now_time))
        status = "IN"
    else:
        # Open session exists -> Mark "OUT"
        conn.execute('UPDATE attendance SET out_time = ? WHERE id = ?', (now_time, att['id']))
        status = "OUT"

    conn.commit()
    conn.close()



    return jsonify({
        'message': f'Attendance marked {status} successfully',
        'status': status,
        'user': display_name,
        'time': now_time
    })



@app.route('/api/attendance', methods=['GET'])
@login_required
def get_attendance():
    date_filter = request.args.get('date', 'today')
    conn = get_db()
    
    if date_filter == 'all':
        query = '''
            SELECT a.id, u.name, u.emp_id, a.date, a.in_time, a.out_time
            FROM attendance a
            JOIN users u ON a.user_id = u.id
            ORDER BY a.date DESC, a.in_time DESC
        '''
        logs = conn.execute(query).fetchall()
    else:
        actual_date = datetime.date.today().isoformat() if date_filter == 'today' else date_filter
        query = '''
            SELECT a.id, u.name, u.emp_id, a.date, a.in_time, a.out_time
            FROM attendance a
            JOIN users u ON a.user_id = u.id
            WHERE a.date = ?
            ORDER BY a.in_time DESC
        '''
        logs = conn.execute(query, (actual_date,)).fetchall()
        
    conn.close()
    return jsonify([dict(l) for l in logs])

@app.route('/api/users/<int:user_id>', methods=['GET'])
@login_required
def get_user_details(user_id):
    conn = get_db()
    user = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
    if not user:
        conn.close()
        return jsonify({'error': 'Student not found'}), 404
    
    logs = conn.execute('''
        SELECT id, date, in_time, out_time
        FROM attendance
        WHERE user_id = ?
        ORDER BY date DESC, in_time DESC
    ''', (user_id,)).fetchall()
    
    conn.close()
    
    return jsonify({
        'user': dict(user),
        'history': [dict(l) for l in logs]
    })

@app.route('/api/backup/db')
@login_required
def backup_db():
    if os.path.exists(DATABASE):
        return send_file(DATABASE, as_attachment=True, download_name=f'attendance_backup_{datetime.date.today()}.db')
    return jsonify({'error': 'Database file not found'}), 404

@app.route('/api/backup/csv')
@login_required
def export_csv():
    import csv
    from io import StringIO
    
    conn = get_db()
    query = '''
        SELECT a.date, u.name, u.emp_id, a.in_time, a.out_time
        FROM attendance a
        JOIN users u ON a.user_id = u.id
        ORDER BY a.date DESC, a.in_time DESC
    '''
    logs = conn.execute(query).fetchall()
    conn.close()
    
    si = StringIO()
    cw = csv.writer(si)
    cw.writerow(['Date', 'Name', 'Student ID', 'In Time', 'Out Time'])
    for log in logs:
        cw.writerow([log['date'], log['name'], log['emp_id'], log['in_time'], log['out_time']])
    
    output = BytesIO()
    output.write(si.getvalue().encode('utf-8'))
    output.seek(0)
    
    return send_file(
        output,
        mimetype='text/csv',
        as_attachment=True,
        download_name=f'attendance_export_{datetime.date.today()}.csv'
    )

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
