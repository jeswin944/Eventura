from flask import Blueprint, render_template, request, redirect, url_for, session, flash, current_app
from werkzeug.security import check_password_hash, generate_password_hash
from models.db import get_db_connection
from itsdangerous import URLSafeTimedSerializer
from services.email_service import send_email
from utils.helpers import login_required
import time

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password']

        db = get_db_connection()
        cursor = db.cursor(dictionary=True)

        # 1. Check FACULTY (using email)
        cursor.execute("SELECT * FROM faculty WHERE email=%s", (username,))
        faculty_user = cursor.fetchone()

        if faculty_user and check_password_hash(faculty_user['password'], password):
            session['user_id'] = faculty_user['faculty_id']
            session['role'] = 'faculty'
            session['is_admin'] = (faculty_user['is_admin'] == 1)
            session['name'] = faculty_user['name']
            db.close()
            
            if session['is_admin']:
                return redirect(url_for('admin.admin_dashboard'))
            return redirect(url_for('faculty.faculty_dashboard'))

        # 2. Check STUDENT (using register_number)
        cursor.execute("SELECT * FROM student WHERE register_number=%s", (username,))
        student_user = cursor.fetchone()

        if student_user and check_password_hash(student_user['password'], password):
            session['user_id'] = student_user['student_id']
            session['role'] = 'student'
            session['is_admin'] = False
            session['name'] = student_user['name']
            db.close()
            return redirect(url_for('student.student_dashboard'))

        db.close()
        flash("Invalid credentials", "error")
        return redirect(url_for('auth.login'))

    return render_template('login.html')

@auth_bp.route('/register-user', methods=['POST'])
def register_user():
    time.sleep(3) 
    role = request.form.get('role', 'student')
    if role != 'student':
        flash("Only student registration is allowed here.", "error")
        return redirect(url_for('auth.login'))

    name = request.form['name']
    email = request.form['email']
    department = request.form['department']
    password = request.form['password']
    confirm = request.form['confirm_password']

    if password != confirm:
        flash("Passwords do not match", "error")
        return redirect(url_for('auth.login'))

    hashed = generate_password_hash(password)

    if not request.form.get('reg_no'):
        flash("Register Number is required for Students", "error")
        return redirect(url_for('auth.login'))
    username = request.form['reg_no'].strip()

    try:
        db = get_db_connection()
        cursor = db.cursor(dictionary=True)
        cursor.execute("SELECT student_id FROM student WHERE register_number=%s", (username,))
        if cursor.fetchone():
             db.close()
             flash("Student already registered (Check Reg No)", "error")
             return redirect(url_for('auth.login'))

        cursor.execute("""
            INSERT INTO student (name, register_number, email, department, semester, password)
            VALUES (%s,%s,%s,%s,%s,%s)
        """, (name, username, email, department, request.form['semester'], hashed))

        db.commit()
        db.close()
        flash("Registration successful. Please Login.", "success")
        return redirect(url_for('auth.login'))

    except Exception as e:
        flash(str(e), "error")
        return redirect(url_for('auth.login'))

@auth_bp.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('auth.login'))

@auth_bp.route('/change-password', methods=['POST'])
@login_required # Imported from utils.helpers
def change_password():
    current_password = request.form['current_password']
    new_password = request.form['new_password']
    confirm_password = request.form['confirm_password']
    
    if new_password != confirm_password:
        flash("New passwords do not match.", "error")
        return redirect(request.referrer)
        
    table = 'faculty' if session['role'] == 'faculty' else 'student'
    id_col = 'faculty_id' if session['role'] == 'faculty' else 'student_id'
    
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)
    
    cursor.execute(f"SELECT password FROM {table} WHERE {id_col}=%s", (session['user_id'],))
    user = cursor.fetchone()
    
    if not user or not check_password_hash(user['password'], current_password):
        db.close()
        flash("Incorrect current password.", "error")
        return redirect(request.referrer)
        
    hashed = generate_password_hash(new_password)
    cursor.execute(f"UPDATE {table} SET password=%s WHERE {id_col}=%s", (hashed, session['user_id']))
    db.commit()
    db.close()
    
    flash("Password changed successfully.", "success")
    return redirect(request.referrer)

@auth_bp.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form['email'].strip()
        db = get_db_connection()
        cursor = db.cursor(dictionary=True)
        
        user = None
        role = None
        user_id_field = None
        id_value = None
        
        cursor.execute("SELECT * FROM faculty WHERE email=%s", (email,))
        faculty_user = cursor.fetchone()
        if faculty_user:
            user = faculty_user
            role = 'faculty'
            user_id_field = 'faculty_id'
            id_value = faculty_user['email']
            
        if not user:
            cursor.execute("SELECT * FROM student WHERE email=%s", (email,))
            student_user = cursor.fetchone()
            if student_user:
                user = student_user
                role = 'student'
                user_id_field = 'student_id'
                id_value = student_user['register_number']
        
        db.close()

        if user:
            serializer = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
            token = serializer.dumps({'user_id': user[user_id_field], 'role': role}, salt='password-reset')
            link = url_for('auth.reset_password', token=token, _external=True)
            
            html_body = f"""
            <h3>Password Reset Request</h3>
            <p>Hello {user['name']},</p>
            <p>We received a request to reset your password.</p>
            <p><strong>Your User ID is:</strong> {id_value}</p>
            <p>Click the link below to set a new password:</p>
            <a href="{link}">{link}</a>
            <p>This link expires in 1 hour.</p>
            <p>If you did not request this, please ignore this email.</p>
            """
            
            try:
                send_email("Password Reset Request", [email], html=html_body)
                flash(f"Password reset link sent to {email}. Check your inbox.", "success")
            except Exception as e:
                flash(f"Error preparing email: {str(e)}", "error")
        else:
            flash("Email not found in our records.", "error")
            
        return redirect(url_for('auth.forgot_password'))
        
    return render_template('forgot_password.html')

@auth_bp.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    serializer = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
    try:
        data = serializer.loads(token, salt='password-reset', max_age=3600)
        user_id = data['user_id']
        role = data['role']
    except Exception:
        flash("The password reset link is invalid or has expired.", "error")
        return redirect(url_for('auth.forgot_password'))
    
    if request.method == 'POST':
        password = request.form['password']
        confirm = request.form['confirm_password']
        
        if password != confirm:
            flash("Passwords do not match.", "error")
            return redirect(url_for('auth.reset_password', token=token))
            
        hashed = generate_password_hash(password)
        
        db = get_db_connection()
        cursor = db.cursor()
        if role == 'faculty':
            cursor.execute("UPDATE faculty SET password=%s WHERE faculty_id=%s", (hashed, user_id))
        else:
            cursor.execute("UPDATE student SET password=%s WHERE student_id=%s", (hashed, user_id))
            
        db.commit()
        db.close()
        flash("Password has been reset successfully. Please login.", "success")
        return redirect(url_for('auth.login'))
        
    return render_template('reset_password.html', token=token)
