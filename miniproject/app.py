from flask import Flask, session, render_template, redirect, url_for, flash
from extensions import mail
from models.db import get_db_connection
from routes.auth_routes import auth_bp
from routes.student_routes import student_bp
from routes.faculty_routes import faculty_bp
from routes.admin_routes import admin_bp
from routes.public_routes import public_bp
from routes.common_routes import common_bp
import flask

from dotenv import load_dotenv
from config import Config

load_dotenv()

app = Flask(__name__)
app.config.from_object(Config)

mail.init_app(app)

# Register Blueprints
app.register_blueprint(auth_bp)
app.register_blueprint(student_bp)
app.register_blueprint(faculty_bp)
app.register_blueprint(admin_bp)
app.register_blueprint(public_bp)
app.register_blueprint(common_bp)

# Context Processor for Notifications
@app.context_processor
def inject_notifications():
    if 'user_id' in session:
        try:
            db = get_db_connection()
            cursor = db.cursor(dictionary=True)
            cursor.execute("""
                SELECT COUNT(*) as count FROM notifications 
                WHERE user_id = %s AND user_role = %s AND is_read = 0
            """, (session['user_id'], session.get('role')))
            result = cursor.fetchone()
            db.close()
            return {'unread_notifications': result['count'] if result else 0}
        except:
             return {'unread_notifications': 0}
    return {'unread_notifications': 0}

@app.errorhandler(403)
def forbidden(e):
    flash("Unauthorized access. You do not have permission to view this page.", "error")
    return redirect(url_for('auth.login'))

@app.errorhandler(404)
def not_found(e):
    return render_template('404.html'), 404 # Assuming 404.html exists or simple return

# URL Adapter for Templates (Backward Compatibility)
def legacy_url_for(endpoint, **values):
    mapping = {
        'login': 'auth.login',
        'logout': 'auth.logout',
        'register_user': 'auth.register_user',
        'forgot_password': 'auth.forgot_password',
        'reset_password': 'auth.reset_password',
        'change_password': 'auth.change_password',
        
        'student_dashboard': 'student.student_dashboard',
        'my_registrations': 'student.my_registrations',
        'register_for_event': 'student.register_for_event',
        'cancel_registration': 'student.cancel_registration',
        'submit_feedback': 'student.submit_feedback',
        'student_timetable': 'student.student_timetable',
        'request_onduty': 'student.request_onduty',
        'student_exams': 'student.student_exams',
        'download_certificate': 'student.download_certificate',
        
        'faculty_dashboard': 'faculty.faculty_dashboard',
        'faculty_timetable': 'faculty.faculty_timetable',
        'export_attendance': 'faculty.export_attendance',
        'scan_attendance': 'faculty.scan_attendance',
        
        'admin_dashboard': 'admin.admin_dashboard',
        'create_event': 'admin.create_event',
        'delete_event': 'admin.delete_event',
        'register_faculty': 'admin.register_faculty',
        'manage_users': 'admin.manage_users',
        'edit_student': 'admin.edit_student',
        'delete_student': 'admin.delete_student',
        'edit_faculty': 'admin.edit_faculty',
        'delete_faculty': 'admin.delete_faculty',
        'system_settings': 'admin.system_settings',
        'admin_feedbacks': 'admin.admin_feedbacks',
        'admin_courses': 'admin.admin_courses',
        'delete_course': 'admin.delete_course',
        'manage_courses': 'admin.manage_courses',
        'manage_timetable': 'admin.manage_timetable',
        'delete_timetable_slot_admin': 'admin.delete_timetable_slot_admin',
        'admin_onduty': 'admin.admin_onduty',
        'approve_onduty': 'admin.approve_onduty',
        'admin_exams': 'admin.admin_exams',
        'delete_exam': 'admin.delete_exam',
        'admin_certificates': 'admin.admin_certificates',
        'approve_certificate': 'admin.approve_certificate',
        
        'home': 'public.home',
        'events': 'public.events',
        
        'get_notifications': 'common.get_notifications'
    }
    
    # If endpoint contains dot, it's likely already namespaced
    if '.' not in endpoint:
        endpoint = mapping.get(endpoint, endpoint)
        
    return flask.url_for(endpoint, **values)

app.jinja_env.globals['url_for'] = legacy_url_for

if __name__ == '__main__':
    app.run(debug=True)