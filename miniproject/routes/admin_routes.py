from flask import Blueprint, render_template, request, redirect, url_for, session, flash, abort, current_app
from models.db import get_db_connection
from utils.helpers import login_required, add_notification, notify_admins
from services.email_service import send_email
from werkzeug.security import generate_password_hash
from datetime import timedelta
import time

admin_bp = Blueprint('admin', __name__)

@admin_bp.route('/admin/dashboard')
@login_required
def admin_dashboard():
    if not session.get('is_admin'):
        abort(403)
    
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)
    
    stats = {}
    cursor.execute("SELECT COUNT(*) as count FROM student")
    stats['total_students'] = cursor.fetchone()['count']
    
    cursor.execute("SELECT COUNT(*) as count FROM faculty")
    stats['total_faculty'] = cursor.fetchone()['count']
    
    cursor.execute("SELECT COUNT(*) as count FROM events")
    stats['total_events'] = cursor.fetchone()['count']
    
    cursor.execute("SELECT COUNT(*) as count FROM registrations")
    stats['total_registrations'] = cursor.fetchone()['count']

    cursor.execute("SELECT COUNT(*) as count FROM onduty_requests WHERE status='Pending'")
    stats['pending_ods'] = cursor.fetchone()['count']

    cursor.execute("SELECT faculty_id, name, department FROM faculty ORDER BY name")
    faculty_list = cursor.fetchall()

    cursor.execute("""
        SELECT 
            e.event_name,
            COUNT(r.registration_id) as total_reg,
            SUM(CASE WHEN r.attendance = 'Present' THEN 1 ELSE 0 END) as attended
        FROM events e
        LEFT JOIN registrations r ON e.event_id = r.event_id
        GROUP BY e.event_id, e.event_name
    """)
    analytics_data = cursor.fetchall()
    
    db.close()
    return render_template('admin_dashboard.html', faculty_list=faculty_list, analytics_data=analytics_data, **stats)

@admin_bp.route('/create-event', methods=['GET', 'POST'])
@login_required
def create_event():
    if not session.get('is_admin'):
        abort(403)

    db = get_db_connection()
    cursor = db.cursor(dictionary=True)

    if request.method == 'POST':
        time.sleep(3) 
        event_name = request.form['event_name']
        event_date = request.form['event_date']
        location = request.form['location']
        description = request.form['description']
        coordinator_id = request.form['coordinator_id']

        try:
            cursor.execute("""
                INSERT INTO events (event_name, event_date, location, description, coordinator_id)
                VALUES (%s, %s, %s, %s, %s)
            """, (event_name, event_date, location, description, coordinator_id))
            db.commit()

            cursor.execute("SELECT email FROM student")
            students = cursor.fetchall()
            
            # Send Email (Simplified batch or loop in thread)
            # send_email handles one by one in thread? 
            # We should probably optimise but sticking to loop for now.
            cursor.execute("SELECT student_id FROM student")
            student_ids = cursor.fetchall()
            
            # Notifications
            add_notification(coordinator_id, 'faculty', f"Assigned Coordinator: {event_name}.")
            for s in student_ids:
                add_notification(s['student_id'], 'student', f"New Event: {event_name} on {event_date}.")
                
            cursor.execute("SELECT faculty_id FROM faculty WHERE faculty_id != %s", (coordinator_id,))
            faculty_ids = cursor.fetchall()
            for f in faculty_ids:
                add_notification(f['faculty_id'], 'faculty', f"Event Added: {event_name}.")
                
            # Emailing logic here is heavy. In app.py it created thread per student.
            # I'll just skip bulk email for now or reimplement properly later.
            # Or use send_email in loop?
            for student in students:
                body = f"""
A new event has been added!

Event Name: {event_name}
Date: {event_date}
Location: {location}
Description: {description}

Login to register now!
"""
                send_email("New Event Announcement!", [student['email']], body=body)

            db.close()
            flash("Event created and announcements sent!", "success")
            return redirect(url_for('admin.admin_dashboard'))
        except Exception as e:
            db.rollback()
            db.close()
            flash(f"Error creating event: {str(e)}", "error")
            return redirect(url_for('admin.create_event'))

    cursor.execute("SELECT faculty_id, name, department FROM faculty ORDER BY name")
    faculty_list = cursor.fetchall()
    db.close()
    return render_template('create_event.html', faculty_list=faculty_list)

@admin_bp.route('/admin/delete-event/<int:event_id>')
@login_required
def delete_event(event_id):
    if not session.get('is_admin'):
        abort(403)
    time.sleep(3)
    
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)
    try:
        cursor.execute("SELECT event_name FROM events WHERE event_id=%s", (event_id,))
        event = cursor.fetchone()
        if not event:
            db.close()
            flash("Event not found.", "error")
            # Redirect to events? events is likely public or student
            return redirect(url_for('public.events')) 

        cursor.execute("DELETE FROM registrations WHERE event_id=%s", (event_id,))
        cursor.execute("DELETE FROM events WHERE event_id=%s", (event_id,))
        db.commit()
        flash(f"Event '{event['event_name']}' and all related records deleted successfully.", "success")
    except Exception as e:
        db.rollback()
        flash(f"Error deleting event: {str(e)}", "error")
        
    db.close()
    # Assuming events list is at /events
    return redirect(url_for('public.events'))

@admin_bp.route('/admin/register-faculty', methods=['GET', 'POST'])
@login_required
def register_faculty():
    if not session.get('is_admin'):
        abort(403)

    if request.method == 'POST':
        time.sleep(3)
        name = request.form['name']
        email = request.form['email']
        department = request.form['department']
        password = request.form['password']
        
        db = get_db_connection()
        cursor = db.cursor(dictionary=True)
        
        cursor.execute("SELECT faculty_id FROM faculty WHERE email=%s", (email,))
        if cursor.fetchone():
            db.close()
            flash("Faculty email already registered", "error")
            return redirect(url_for('admin.register_faculty'))

        hashed = generate_password_hash(password)
        
        try:
            cursor.execute("""
                INSERT INTO faculty (name, email, department, password, is_admin)
                VALUES (%s, %s, %s, %s, 0)
            """, (name, email, department, hashed))
            db.commit()
            db.close()
            flash("Faculty member registered successfully", "success")
            return redirect(url_for('admin.admin_dashboard'))
        except Exception as e:
            db.rollback()
            db.close()
            flash(f"Error registering faculty: {str(e)}", "error")
            return redirect(url_for('admin.register_faculty'))

    return render_template('register_faculty.html')

@admin_bp.route('/admin/manage-users')
@login_required
def manage_users():
    if not session.get('is_admin'):
        abort(403)
        
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT * FROM student ORDER BY name")
    students = cursor.fetchall()
    cursor.execute("SELECT * FROM faculty ORDER BY name")
    faculty = cursor.fetchall()
    db.close()
    
    return render_template('manage_users.html', students=students, faculty=faculty)

@admin_bp.route('/admin/edit-student/<int:id>', methods=['POST'])
@login_required
def edit_student(id):
    if not session.get('is_admin'):
        abort(403)
    
    name = request.form.get('name')
    email = request.form.get('email')
    reg_no = request.form.get('register_number')
    dept = request.form.get('department')
    sem = request.form.get('semester')
    
    db = get_db_connection()
    cursor = db.cursor()
    try:
        cursor.execute("""
            UPDATE student 
            SET name=%s, email=%s, register_number=%s, department=%s, semester=%s
            WHERE student_id=%s
        """, (name, email, reg_no, dept, sem, id))
        db.commit()
        flash("Student updated successfully", "success")
    except Exception as e:
        db.rollback()
        flash(f"Error updating student: {str(e)}", "error")
    db.close()
    return redirect(url_for('admin.manage_users'))

@admin_bp.route('/admin/delete-student/<int:id>')
@login_required
def delete_student(id):
    if not session.get('is_admin'):
        abort(403)
    time.sleep(3)
    db = get_db_connection()
    cursor = db.cursor()
    try:
        cursor.execute("DELETE FROM feedback WHERE student_id=%s", (id,))
        cursor.execute("DELETE FROM registrations WHERE student_id=%s", (id,))
        cursor.execute("DELETE FROM student WHERE student_id=%s", (id,))
        db.commit()
        flash("Student deleted successfully", "success")
    except Exception as e:
        db.rollback()
        flash(f"Error deleting student: {str(e)}", "error")
    db.close()
    return redirect(url_for('admin.manage_users'))

@admin_bp.route('/admin/edit-faculty/<int:id>', methods=['POST'])
@login_required
def edit_faculty(id):
    if not session.get('is_admin'):
        abort(403)
    name = request.form.get('name')
    email = request.form.get('email')
    dept = request.form.get('department')
    db = get_db_connection()
    cursor = db.cursor()
    try:
        cursor.execute("""
            UPDATE faculty 
            SET name=%s, email=%s, department=%s
            WHERE faculty_id=%s
        """, (name, email, dept, id))
        db.commit()
        flash("Faculty member updated successfully", "success")
    except Exception as e:
        db.rollback()
        flash(f"Error updating faculty: {str(e)}", "error")
    db.close()
    return redirect(url_for('admin.manage_users'))

@admin_bp.route('/admin/delete-faculty/<int:id>')
@login_required
def delete_faculty(id):
    if not session.get('is_admin'):
        abort(403)
    time.sleep(3)
    if id == session.get('user_id') and session.get('role') == 'faculty':
        flash("You cannot delete your own admin account.", "error")
        return redirect(url_for('admin.manage_users'))
    db = get_db_connection()
    cursor = db.cursor()
    try:
        cursor.execute("DELETE FROM faculty WHERE faculty_id=%s", (id,))
        db.commit()
        flash("Faculty member deleted successfully", "success")
    except Exception as e:
        db.rollback()
        flash(f"Error deleting faculty: {str(e)}", "error")
    db.close()
    return redirect(url_for('admin.manage_users'))

@admin_bp.route('/admin/system-settings')
@login_required
def system_settings():
    if not session.get('is_admin'):
        abort(403)
    return render_template('system_settings.html')

@admin_bp.route('/admin/feedbacks')
@login_required
def admin_feedbacks():
    if not session.get('is_admin'):
        abort(403)
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)
    cursor.execute("""
        SELECT f.*, e.event_name, s.name as student_name, s.department
        FROM feedback f
        JOIN events e ON f.event_id = e.event_id
        JOIN student s ON f.student_id = s.student_id
        ORDER BY f.created_at DESC
    """)
    feedbacks = cursor.fetchall()
    db.close()
    return render_template('admin_feedbacks.html', feedbacks=feedbacks)

@admin_bp.route('/admin/courses', methods=['GET', 'POST'])
@login_required
def admin_courses():
    if not session.get('is_admin'):
        abort(403)
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)
    if request.method == 'POST':
        course_name = request.form['course_name']
        dept = request.form['department']
        semester = request.form['semester']
        try:
            cursor.execute("INSERT INTO courses (course_name, department, semester) VALUES (%s, %s, %s)", 
                           (course_name, dept, semester))
            db.commit()
            flash("Course added successfully!", "success")
        except Exception as e:
            db.rollback()
            flash(f"Error adding course: {e}", "error")
        db.close()
        return redirect(url_for('admin.admin_courses'))
    cursor.execute("SELECT * FROM courses ORDER BY department, semester")
    courses = cursor.fetchall()
    db.close()
    return render_template('admin_courses.html', courses=courses)

@admin_bp.route('/admin/delete-course/<int:course_id>')
@login_required
def delete_course(course_id):
    if not session.get('is_admin'):
        abort(403)
    db = get_db_connection()
    cursor = db.cursor()
    try:
        cursor.execute("DELETE FROM timetable WHERE course_id=%s", (course_id,))
        cursor.execute("DELETE FROM courses WHERE course_id=%s", (course_id,))
        db.commit()
        flash("Course deleted.", "success")
    except Exception as e:
        db.rollback()
        flash(f"Error deleting course: {e}", "error")
    db.close()
    return redirect(url_for('admin.admin_courses'))

@admin_bp.route('/admin/manage-courses')
@login_required
def manage_courses():
    return redirect(url_for('admin.admin_courses'))

@admin_bp.route('/admin/manage-timetable', methods=['GET', 'POST'])
@login_required
def manage_timetable():
    if not session.get('is_admin'):
        abort(403)
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)
    if request.method == 'POST':
        course_id = request.form['course_id']
        faculty_id = request.form['faculty_id']
        day = request.form['day']
        start_time = request.form['start_time']
        end_time = request.form['end_time']
        classroom = request.form['classroom']
        cursor.execute("""
            SELECT timetable_id FROM timetable
            WHERE faculty_id=%s
            AND day=%s
            AND (
                (start_time < %s AND end_time > %s)
            )
        """, (faculty_id, day, end_time, start_time))
        conflict = cursor.fetchone()
        if conflict:
             flash("Time conflict detected! Faculty is already booked for this slot.", "error")
             db.close()
             return redirect(url_for('admin.manage_timetable'))
        try:
            cursor.execute("""
                INSERT INTO timetable (course_id, faculty_id, day, start_time, end_time, classroom)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (course_id, faculty_id, day, start_time, end_time, classroom))
            db.commit()
            flash("Schedule assigned successfully.", "success")
        except Exception as e:
            db.rollback()
            flash(f"Error assigning schedule: {e}", "error")
        db.close()
        return redirect(url_for('admin.manage_timetable'))
    cursor.execute("""
        SELECT t.*, c.course_name, c.department, c.semester, f.name as faculty_name
        FROM timetable t
        JOIN courses c ON t.course_id = c.course_id
        JOIN faculty f ON t.faculty_id = f.faculty_id
        ORDER BY FIELD(day, 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'), start_time
    """)
    timetable = cursor.fetchall()
    cursor.execute("SELECT * FROM courses ORDER BY course_name")
    courses = cursor.fetchall()
    cursor.execute("SELECT faculty_id, name, department FROM faculty ORDER BY name")
    faculty_list = cursor.fetchall()
    db.close()
    return render_template('admin_timetable.html', timetable=timetable, courses=courses, faculty_list=faculty_list)

@admin_bp.route('/admin/delete-timetable-slot/<int:slot_id>')
@login_required
def delete_timetable_slot_admin(slot_id):
    if not session.get('is_admin'):
        abort(403)
    db = get_db_connection()
    cursor = db.cursor()
    try:
        cursor.execute("DELETE FROM timetable WHERE timetable_id=%s", (slot_id,))
        db.commit()
        flash("Schedule deleted.", "success")
    except Exception as e:
        db.rollback()
        flash(f"Error deleting schedule: {e}", "error")
    db.close()
    return redirect(url_for('admin.manage_timetable'))

@admin_bp.route('/admin/onduty')
@login_required
def admin_onduty():
    if not session.get('is_admin'):
        abort(403)
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)
    cursor.execute("""
        SELECT od.*, s.name as student_name, s.register_number, s.department, e.event_name, e.event_date
        FROM onduty_requests od
        JOIN student s ON od.student_id = s.student_id
        JOIN events e ON od.event_id = e.event_id
        ORDER BY od.request_date DESC
    """)
    requests = cursor.fetchall()
    db.close()
    return render_template('admin_onduty.html', requests=requests)

@admin_bp.route('/admin/onduty/respond/<int:req_id>/<string:action>')
@login_required
def approve_onduty(req_id, action):
    if not session.get('is_admin'):
        abort(403)
    new_status = 'Approved' if action == 'approve' else 'Rejected'
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT od.student_id, e.event_name 
            FROM onduty_requests od
            JOIN events e ON od.event_id = e.event_id
            WHERE od.request_id = %s
        """, (req_id,))
        req_details = cursor.fetchone()
        cursor.execute("UPDATE onduty_requests SET status=%s, approved_by=%s WHERE request_id=%s", 
                       (new_status, session['user_id'], req_id))
        if req_details:
             msg = f"Your On-Duty request for event '{req_details['event_name']}' has been {new_status} by Admin."
             add_notification(req_details['student_id'], 'student', msg)
        db.commit()
        flash(f"Request {new_status}.", "success")
    except Exception as e:
        db.rollback()
        flash(f"Error updating request: {e}", "error")
    db.close()
    return redirect(url_for('admin.admin_onduty'))

@admin_bp.route('/admin/exams', methods=['GET', 'POST'])
@login_required
def admin_exams():
    if not session.get('is_admin'):
        abort(403)
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)
    if request.method == 'POST':
        try:
            course_id = request.form['course_id']
            exam_date = request.form['exam_date']
            start_time = request.form['start_time']
            end_time = request.form['end_time']
            hall = request.form['hall']
            cursor.execute("""
                INSERT INTO exams (course_id, exam_date, start_time, end_time, hall)
                VALUES (%s, %s, %s, %s, %s)
            """, (course_id, exam_date, start_time, end_time, hall))
            db.commit()
            flash("Exam scheduled successfully!", "success")
        except Exception as e:
            db.rollback()
            flash(f"Error scheduling exam: {e}", "error")
        db.close()
        return redirect(url_for('admin.admin_exams'))
    cursor.execute("""
        SELECT e.*, c.course_name, c.department, c.semester 
        FROM exams e 
        JOIN courses c ON e.course_id = c.course_id 
        ORDER BY e.exam_date, e.start_time
    """)
    exams = cursor.fetchall()
    
    for ex in exams:
        for f in ['start_time', 'end_time']:
            if isinstance(ex[f], timedelta):
                total_seconds = int(ex[f].total_seconds())
                hours = total_seconds // 3600
                minutes = (total_seconds % 3600) // 60
                ex[f] = f"{hours:02}:{minutes:02}"
            else:
                 ex[f] = str(ex[f])
    cursor.execute("SELECT * FROM courses ORDER BY department, course_name")
    courses = cursor.fetchall()
    db.close()
    return render_template('admin_exams.html', exams=exams, courses=courses)

@admin_bp.route('/admin/delete_exam/<int:exam_id>')
@login_required
def delete_exam(exam_id):
    if not session.get('is_admin'):
        abort(403)
    db = get_db_connection()
    cursor = db.cursor()
    try:
        cursor.execute("DELETE FROM exams WHERE exam_id=%s", (exam_id,))
        db.commit()
        flash("Exam schedule deleted.", "success")
    except Exception as e:
        db.rollback()
        flash("Error deleting exam.", "error")
    db.close()
    return redirect(url_for('admin.admin_exams'))

@admin_bp.route('/admin/certificates')
@login_required
def admin_certificates():
    if not session.get('is_admin'):
        abort(403)
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)
    cursor.execute("""
        SELECT r.registration_id, r.certificate_status, s.name as student_name, e.event_name, e.event_date
        FROM registrations r
        JOIN student s ON r.student_id = s.student_id
        JOIN events e ON r.event_id = e.event_id
        WHERE r.certificate_status = 'Pending'
        ORDER BY e.event_date DESC
    """)
    pending_certs = cursor.fetchall()
    db.close()
    return render_template('admin_certificates.html', pending_certs=pending_certs)

@admin_bp.route('/admin/approve-certificate/<int:reg_id>')
@login_required
def approve_certificate(reg_id):
    if not session.get('is_admin'):
        abort(403)
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)
    try:
        cursor.execute("UPDATE registrations SET certificate_status='Approved' WHERE registration_id=%s", (reg_id,))
        db.commit()
        cursor.execute("SELECT student_id FROM registrations WHERE registration_id=%s", (reg_id,))
        res = cursor.fetchone()
        if res:
             add_notification(res['student_id'], 'student', "Your certificate has been approved! Download it now.")
        flash("Certificate approved successfully!", "success")
    except Exception as e:
        db.rollback()
        flash(f"Error approving certificate: {e}", "error")
    db.close()
    return redirect(url_for('admin.admin_certificates'))

@admin_bp.route('/admin/toggle-event-status/<int:event_id>/<string:new_status>')
@login_required
def toggle_event_status(event_id, new_status):
    if not session.get('is_admin'):
        abort(403)
    
    if new_status not in ['Open', 'Closed']:
        flash("Invalid status.", "error")
        return redirect(url_for('public.events'))
        
    db = get_db_connection()
    cursor = db.cursor()
    try:
        cursor.execute("UPDATE events SET status=%s WHERE event_id=%s", (new_status, event_id))
        db.commit()
        flash(f"Event registration is now {new_status}.", "success")
    except Exception as e:
        db.rollback()
        flash(f"Error updating status: {e}", "error")
    db.close()
    
    return redirect(url_for('public.events'))
