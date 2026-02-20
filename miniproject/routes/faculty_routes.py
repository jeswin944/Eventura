from flask import Blueprint, render_template, request, redirect, url_for, session, flash, abort, make_response
from models.db import get_db_connection
from utils.helpers import login_required, role_required, add_notification, notify_admins
import openpyxl
import io

faculty_bp = Blueprint('faculty', __name__)

@faculty_bp.route('/faculty/dashboard')
@login_required
@role_required('faculty')
def faculty_dashboard():
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)
    
    cursor.execute("""
        SELECT e.*, 
        COUNT(r.registration_id) as total_reg_count,
        SUM(CASE WHEN r.attendance = 'Present' THEN 1 ELSE 0 END) as attended_count
        FROM events e
        LEFT JOIN registrations r ON e.event_id = r.event_id
        WHERE e.coordinator_id = %s
        GROUP BY e.event_id
        ORDER BY e.event_date
    """, (session['user_id'],))
    events = cursor.fetchall()
    
    for e in events:
        total = e['total_reg_count']
        attended = e['attended_count'] or 0
        e['attendance_percentage'] = round((attended / total) * 100) if total > 0 else 0
    
    total_events = len(events)
    total_registrations = sum(e['total_reg_count'] for e in events)
    total_attendance = sum(e['attended_count'] for e in events if e['attended_count'])
    
    attendance_rate = 0
    if total_registrations > 0:
        attendance_rate = round((total_attendance / total_registrations) * 100, 1)

    analytics_data = []
    for e in events:
        analytics_data.append({
            'event_name': e['event_name'],
            'total_reg': e['total_reg_count'],
            'attended': int(e['attended_count']) if e['attended_count'] else 0
        })
    
    db.close()
    return render_template('faculty_dashboard.html', 
                           events=events,
                           total_events=total_events,
                           total_registrations=total_registrations,
                           attendance_rate=attendance_rate,
                           analytics_data=analytics_data)

@faculty_bp.route('/export-attendance/<int:event_id>')
@login_required
@role_required('faculty')
def export_attendance(event_id):
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)
    
    cursor.execute("SELECT event_name FROM events WHERE event_id=%s AND coordinator_id=%s", (event_id, session['user_id']))
    event = cursor.fetchone()
    if not event:
        db.close()
        abort(403)
        
    cursor.execute("""
        SELECT s.name, s.register_number, s.department, s.email, s.semester, r.attendance, r.certificate_status
        FROM registrations r
        JOIN student s ON r.student_id = s.student_id
        WHERE r.event_id = %s
        ORDER BY s.name
    """, (event_id,))
    attendees = cursor.fetchall()
    db.close()
    
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Attendance Sheet"
    
    headers = ["Name", "Register Number", "Department", "Semester", "Email", "Attendance Status", "Certificate Status"]
    ws.append(headers)
    
    for person in attendees:
        attendance = person['attendance'] if person['attendance'] else 'Absent'
        cert_status = person['certificate_status'] if person['certificate_status'] else 'Not Issued'
        ws.append([
            person['name'],
            person['register_number'],
            person['department'],
            person['semester'],
            person['email'],
            attendance,
            cert_status
        ])
        
    for col in ws.columns:
        max_length = 0
        column = col[0].column_letter
        for cell in col:
            try:
                if len(str(cell.value)) > max_length:
                    max_length = len(str(cell.value))
            except:
                pass
        adjusted_width = (max_length + 2)
        ws.column_dimensions[column].width = adjusted_width

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    
    return make_response(output.getvalue(), 200, {
        "Content-Disposition": f"attachment; filename=Attendance_{event['event_name']}.xlsx",
        "Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    })

@faculty_bp.route('/scan-attendance', methods=['GET', 'POST'])
@login_required
@role_required('faculty')
def scan_attendance():
    if request.method == 'POST':
        qr_token = request.form.get('qr_token')
        
        if not qr_token:
            return "No token provided", 400

        db = get_db_connection()
        cursor = db.cursor(dictionary=True)
        
        cursor.execute("""
            SELECT r.registration_id, s.student_id, s.name, e.event_name 
            FROM registrations r 
            JOIN student s ON r.student_id = s.student_id 
            JOIN events e ON r.event_id = e.event_id 
            WHERE r.qr_token = %s
        """, (qr_token,))
        registration = cursor.fetchone()

        if registration:
            cursor.execute("""
                UPDATE registrations 
                SET attendance = 'Present', certificate_status = 'Pending' 
                WHERE qr_token = %s
            """, (qr_token,))
            db.commit()

            add_notification(registration['student_id'], 'student', f"Attendance marked: {registration['event_name']}.")
            notify_admins(f"Certificate Pending Approval: {registration['name']} - {registration['event_name']}.")
            
            db.close()
            return f"Success: Attendance marked for {registration['name']} (Event: {registration['event_name']})"
        else:
            db.close()
            return "Error: Invalid QR Code", 404

    return render_template('scan_attendance.html')

@faculty_bp.route('/faculty/timetable')
@login_required
@role_required('faculty')
def faculty_timetable():
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)
    
    cursor.execute("""
        SELECT t.*, c.course_name, c.semester, c.department 
        FROM timetable t 
        JOIN courses c ON t.course_id = c.course_id 
        WHERE t.faculty_id = %s 
        ORDER BY FIELD(day, 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'), start_time
    """, (session['user_id'],))
    timetable = cursor.fetchall()
    
    db.close()
    return render_template('faculty_timetable.html', timetable=timetable, courses=[])
