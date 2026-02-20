from flask import Blueprint, render_template, session, request
from models.db import get_db_connection

public_bp = Blueprint('public', __name__)

@public_bp.route('/')
def home():
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)
    
    if session.get('role') == 'student':
        cursor.execute("""
            SELECT e.*, 
            CASE WHEN r.registration_id IS NOT NULL THEN 1 ELSE 0 END as is_registered
            FROM events e
            LEFT JOIN registrations r ON e.event_id = r.event_id AND r.student_id = %s
            ORDER BY e.event_date
        """, (session['user_id'],))
    else:
        cursor.execute("SELECT * FROM events ORDER BY event_date")
    
    events = cursor.fetchall()
    db.close()
    return render_template('index.html', events=events)

@public_bp.route('/events')
def events():
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)
    
    # Pagination Logic
    page = request.args.get('page', 1, type=int)
    per_page = 6
    offset = (page - 1) * per_page
    
    # Get total count
    cursor.execute("SELECT COUNT(*) as total FROM events")
    total_events = cursor.fetchone()['total']
    total_pages = (total_events + per_page - 1) // per_page
    
    # Fetch subset
    cursor.execute("SELECT * FROM events ORDER BY event_date DESC LIMIT %s OFFSET %s", (per_page, offset))
    events = cursor.fetchall()
    
    # Calculate Deadline Status
    from datetime import datetime, timedelta
    current_date = datetime.now().date()
    
    for event in events:
        e_date = event['event_date']
        if isinstance(e_date, str):
            e_date = datetime.strptime(e_date, '%Y-%m-%d').date()
            
        # Deadline is 2 days before event
        # If today is 18th, event is 20th. 20-18=2. Allowed.
        # If today is 19th, event is 20th. 20-19=1. Blocked.
        if (e_date - current_date).days < 2:
            event['deadline_passed'] = True
        else:
            event['deadline_passed'] = False

    db.close()
    return render_template('events.html', events=events, page=page, total_pages=total_pages)
