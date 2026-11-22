import os

FILES = {
    "requirements.txt": """Flask==3.0.0
Flask-SQLAlchemy==3.1.1
Flask-Login==0.6.3
Flask-WTF==1.2.2
xhtml2pdf==0.2.17
waitress>=3.0,<4
""",

    "app.py": r'''"""
CMSC 308 - Group 3
Classroom Scheduling and Academic Timetabling System
"""

import os
from datetime import time, datetime
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.exc import IntegrityError
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY') or os.urandom(32)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(BASE_DIR, 'timetable.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message_category = 'warning'

DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']
TIME_SLOTS = [
    (time(7, 0), time(8, 0)), (time(8, 0), time(9, 0)), (time(9, 0), time(10, 0)),
    (time(10, 0), time(11, 0)), (time(11, 0), time(12, 0)), (time(12, 0), time(13, 0)),
    (time(13, 0), time(14, 0)), (time(14, 0), time(15, 0)), (time(15, 0), time(16, 0)),
    (time(16, 0), time(17, 0)), (time(17, 0), time(18, 0)),
]

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), default='Instructor') 

class Term(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), unique=True, nullable=False)
    schedules = db.relationship('Schedule', backref='term', lazy=True)

class Course(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(20), unique=True, nullable=False)
    title = db.Column(db.String(120), nullable=False)
    units = db.Column(db.Integer, default=3)
    room_type = db.Column(db.String(20), default='lecture')
    schedules = db.relationship('Schedule', backref='course', lazy=True)

class Faculty(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    department = db.Column(db.String(80))
    schedules = db.relationship('Schedule', backref='faculty', lazy=True)
    availabilities = db.relationship('Availability', backref='faculty', lazy=True)

class Room(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(20), unique=True, nullable=False)
    capacity = db.Column(db.Integer, default=30)
    room_type = db.Column(db.String(20), default='lecture')
    schedules = db.relationship('Schedule', backref='room', lazy=True)
    availabilities = db.relationship('Availability', backref='room', lazy=True)

class Section(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    program = db.Column(db.String(50))
    size = db.Column(db.Integer, default=30)
    schedules = db.relationship('Schedule', backref='section', lazy=True)

class Availability(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    faculty_id = db.Column(db.Integer, db.ForeignKey('faculty.id'), nullable=True)
    room_id = db.Column(db.Integer, db.ForeignKey('room.id'), nullable=True)
    day = db.Column(db.String(3), nullable=False)
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)

class Schedule(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    term_id = db.Column(db.Integer, db.ForeignKey('term.id'), nullable=False)
    course_id = db.Column(db.Integer, db.ForeignKey('course.id'), nullable=False)
    faculty_id = db.Column(db.Integer, db.ForeignKey('faculty.id'), nullable=False)
    section_id = db.Column(db.Integer, db.ForeignKey('section.id'), nullable=False)
    room_id = db.Column(db.Integer, db.ForeignKey('room.id'), nullable=True)
    day = db.Column(db.String(3), nullable=True)
    start_time = db.Column(db.Time, nullable=True)
    end_time = db.Column(db.Time, nullable=True)

    @property
    def is_pending(self):
        return self.room_id is None or self.day is None

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

class ConflictError(Exception): pass

def overlaps(s1, e1, s2, e2):
    return s1 < e2 and e1 > s2

def check_schedule_conflicts(new, existing_schedules, exclude_id=None):
    conflicts = []
    if new.get('day') is None or new.get('start_time') is None or new.get('end_time') is None:
        return conflicts

    for s in existing_schedules:
        if s.id == exclude_id: continue
        if s.day is None or s.start_time is None or s.end_time is None: continue
        if s.day != new['day']: continue
        if not overlaps(new['start_time'], new['end_time'], s.start_time, s.end_time): continue
        
        if new.get('faculty_id') and s.faculty_id == new['faculty_id']:
            conflicts.append(f"Faculty conflict: {s.faculty.name} already teaching {s.course.code} at {s.start_time.strftime('%H:%M')}")
        if new.get('room_id') and s.room_id == new['room_id']:
            conflicts.append(f"Room conflict: {s.room.code} already booked for {s.course.code} at {s.start_time.strftime('%H:%M')}")
        if new.get('section_id') and s.section_id == new['section_id']:
            conflicts.append(f"Section conflict: {s.section.name} already has {s.course.code} at {s.start_time.strftime('%H:%M')}")

    for avail in Availability.query.filter_by(day=new['day']).all():
        if not overlaps(new['start_time'], new['end_time'], avail.start_time, avail.end_time): continue
        if avail.faculty_id and avail.faculty_id == new.get('faculty_id'):
            conflicts.append(f"Faculty {avail.faculty.name} is unavailable at this time")
        if avail.room_id and avail.room_id == new.get('room_id'):
            conflicts.append(f"Room {avail.room.code} is unavailable at this time")
    return conflicts

def check_room_suitability(room, section, course):
    problems = []
    if room.capacity < section.size:
        problems.append(f"Room {room.code} capacity ({room.capacity}) is smaller than section {section.name} ({section.size})")
    if course.room_type == 'lab' and room.room_type != 'lab':
        problems.append(f"Course {course.code} requires a lab, but {room.code} is a {room.room_type} room")
    return problems

def auto_generate(term_id):
    pending = Schedule.query.filter_by(term_id=term_id, room_id=None).all()
    pending.sort(key=lambda s: (0 if s.course.room_type == 'lab' else 1, -s.section.size))
    assigned_count, still_unassigned = 0, []

    for sched in pending:
        placed = False
        for day in DAYS:
            for start, end in TIME_SLOTS:
                for room in Room.query.all():
                    if check_room_suitability(room, sched.section, sched.course): continue
                    candidate = {'day': day, 'start_time': start, 'end_time': end, 'room_id': room.id, 'faculty_id': sched.faculty_id, 'section_id': sched.section_id, 'course_id': sched.course_id}
                    existing = Schedule.query.filter(Schedule.term_id == term_id, Schedule.room_id.isnot(None)).all()
                    if not check_schedule_conflicts(candidate, existing, exclude_id=sched.id):
                        sched.day, sched.start_time, sched.end_time, sched.room_id = day, start, end, room.id
                        db.session.commit()
                        assigned_count += 1
                        placed = True
                        break
                if placed: break
            if placed: break
        if not placed: still_unassigned.append(sched)
    return assigned_count, still_unassigned

def parse_time(value):
    if not value: return None
    try: return datetime.strptime(value, '%H:%M').time()
    except ValueError: return None

def build_timetable(schedules):
    grid = {}
    for s in schedules:
        if s.day and s.start_time: grid[(s.day, s.start_time.strftime('%H:%M'))] = s
    return grid

# ============================================================
# AUTH ROUTES
# ============================================================
@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated: return redirect(url_for('index'))
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form.get('username')).first()
        if user and check_password_hash(user.password_hash, request.form.get('password')):
            login_user(user)
            return redirect(url_for('index'))
        flash('Invalid username or password.', 'danger')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated: return redirect(url_for('index'))
    if request.method == 'POST':
        username = request.form.get('username')
        if User.query.filter_by(username=username).first():
            flash('Username already exists.', 'danger')
        else:
            db.session.add(User(username=username, password_hash=generate_password_hash(request.form.get('password'))))
            db.session.commit()
            flash('Account created! Please log in.', 'success')
            return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

# ============================================================
# MAIN ROUTES
# ============================================================
@app.route('/')
@login_required
def index():
    # Get all schedules for the dashboard view
    all_scheds = Schedule.query.filter(Schedule.room_id.isnot(None)).all()
    grid = build_timetable(all_scheds)
    
    stats = {
        'courses': Course.query.count(), 
        'faculty': Faculty.query.count(), 
        'rooms': Room.query.count(), 
        'sections': Section.query.count(), 
        'schedules': len(all_scheds), 
        'pending': Schedule.query.filter_by(room_id=None).count()
    }
    return render_template('index.html', stats=stats, grid=grid, days=DAYS, time_slots=TIME_SLOTS)

@app.route('/academic')
@login_required
def academic():
    return render_template('academic.html', courses=Course.query.order_by(Course.code).all(), faculty=Faculty.query.order_by(Faculty.name).all(), rooms=Room.query.order_by(Room.code).all(), sections=Section.query.order_by(Section.name).all(), terms=Term.query.all())

@app.route('/academic/course/add', methods=['POST'])
@login_required
def add_course():
    code, title = request.form.get('code', '').strip().upper(), request.form.get('title', '').strip()
    try: units = int(request.form.get('units', 3))
    except ValueError: flash('Units must be a number.', 'danger'); return redirect(url_for('academic'))
    if not code or not title or units <= 0: flash('Code, title, and positive units required.', 'danger'); return redirect(url_for('academic'))
    try:
        db.session.add(Course(code=code, title=title, units=units, room_type=request.form.get('room_type', 'lecture')))
        db.session.commit(); flash(f"Course '{code}' added.", 'success')
    except IntegrityError: db.session.rollback(); flash(f"Course code '{code}' already exists.", 'danger')
    return redirect(url_for('academic'))

@app.route('/academic/course/<int:id>/delete', methods=['POST'])
@login_required
def delete_course(id):
    c = db.session.get(Course, id)
    if not c: flash('Course not found.', 'danger')
    elif c.schedules: flash(f"Cannot delete {c.code}: schedule(s) reference it.", 'danger')
    else: db.session.delete(c); db.session.commit(); flash(f"Course '{c.code}' deleted.", 'success')
    return redirect(url_for('academic'))

@app.route('/academic/faculty/add', methods=['POST'])
@login_required
def add_faculty():
    name, dept = request.form.get('name', '').strip(), request.form.get('department', '').strip()
    if not name: flash('Faculty name is required.', 'danger'); return redirect(url_for('academic'))
    db.session.add(Faculty(name=name, department=dept))
    db.session.commit(); flash(f"Faculty '{name}' added.", 'success')
    return redirect(url_for('academic'))

@app.route('/academic/faculty/<int:id>/delete', methods=['POST'])
@login_required
def delete_faculty(id):
    f = db.session.get(Faculty, id)
    if not f: flash('Faculty not found.', 'danger')
    elif f.schedules: flash(f"Cannot delete {f.name}: schedule(s) reference them.", 'danger')
    else: db.session.delete(f); db.session.commit(); flash(f"Faculty '{f.name}' deleted.", 'success')
    return redirect(url_for('academic'))

@app.route('/academic/room/add', methods=['POST'])
@login_required
def add_room():
    code = request.form.get('code', '').strip().upper()
    try: cap = int(request.form.get('capacity', 30))
    except ValueError: flash('Capacity must be a number.', 'danger'); return redirect(url_for('academic'))
    if not code or cap <= 0: flash('Code and positive capacity required.', 'danger'); return redirect(url_for('academic'))
    try:
        db.session.add(Room(code=code, capacity=cap, room_type=request.form.get('room_type', 'lecture')))
        db.session.commit(); flash(f"Room '{code}' added.", 'success')
    except IntegrityError: db.session.rollback(); flash(f"Room code '{code}' already exists.", 'danger')
    return redirect(url_for('academic'))

@app.route('/academic/room/<int:id>/delete', methods=['POST'])
@login_required
def delete_room(id):
    r = db.session.get(Room, id)
    if not r: flash('Room not found.', 'danger')
    elif r.schedules: flash(f"Cannot delete {r.code}: schedule(s) reference it.", 'danger')
    else: db.session.delete(r); db.session.commit(); flash(f"Room '{r.code}' deleted.", 'success')
    return redirect(url_for('academic'))

@app.route('/academic/section/add', methods=['POST'])
@login_required
def add_section():
    name = request.form.get('name', '').strip().upper()
    try: size = int(request.form.get('size', 30))
    except ValueError: flash('Section size must be a number.', 'danger'); return redirect(url_for('academic'))
    if not name or size <= 0: flash('Name and positive size required.', 'danger'); return redirect(url_for('academic'))
    try:
        db.session.add(Section(name=name, program=request.form.get('program', '').strip(), size=size))
        db.session.commit(); flash(f"Section '{name}' added.", 'success')
    except IntegrityError: db.session.rollback(); flash(f"Section '{name}' already exists.", 'danger')
    return redirect(url_for('academic'))

@app.route('/academic/section/<int:id>/delete', methods=['POST'])
@login_required
def delete_section(id):
    s = db.session.get(Section, id)
    if not s: flash('Section not found.', 'danger')
    elif s.schedules: flash(f"Cannot delete {s.name}: schedule(s) reference it.", 'danger')
    else: db.session.delete(s); db.session.commit(); flash(f"Section '{s.name}' deleted.", 'success')
    return redirect(url_for('academic'))

@app.route('/academic/term/add', methods=['POST'])
@login_required
def add_term():
    name = request.form.get('name', '').strip()
    if not name: flash('Term name required.', 'danger'); return redirect(url_for('academic'))
    try:
        db.session.add(Term(name=name)); db.session.commit(); flash(f"Term '{name}' added.", 'success')
    except IntegrityError: db.session.rollback(); flash(f"Term '{name}' already exists.", 'danger')
    return redirect(url_for('academic'))

@app.route('/academic/term/<int:id>/delete', methods=['POST'])
@login_required
def delete_term(id):
    t = db.session.get(Term, id)
    if not t: flash('Term not found.', 'danger')
    elif t.schedules: flash(f"Cannot delete {t.name}: schedule(s) reference it.", 'danger')
    else: db.session.delete(t); db.session.commit(); flash(f"Term '{t.name}' deleted.", 'success')
    return redirect(url_for('academic'))

@app.route('/availability')
@login_required
def availability():
    return render_template('availability.html', availabilities=Availability.query.order_by(Availability.day).all(), faculty=Faculty.query.order_by(Faculty.name).all(), rooms=Room.query.order_by(Room.code).all(), days=DAYS)

@app.route('/availability/add', methods=['POST'])
@login_required
def add_availability():
    entity, day = request.form.get('entity', ''), request.form.get('day', '')
    start, end = parse_time(request.form.get('start_time', '')), parse_time(request.form.get('end_time', ''))
    if not entity or day not in DAYS or not start or not end or start >= end:
        flash('Invalid entity, day, or time range.', 'danger'); return redirect(url_for('availability'))
    kind, _, eid = entity.partition(':')
    try: eid = int(eid)
    except ValueError: flash('Invalid entity.', 'danger'); return redirect(url_for('availability'))
    if kind == 'faculty': db.session.add(Availability(faculty_id=eid, day=day, start_time=start, end_time=end))
    elif kind == 'room': db.session.add(Availability(room_id=eid, day=day, start_time=start, end_time=end))
    db.session.commit(); flash('Unavailability block added.', 'success')
    return redirect(url_for('availability'))

@app.route('/availability/<int:id>/delete', methods=['POST'])
@login_required
def delete_availability(id):
    a = db.session.get(Availability, id)
    if a: db.session.delete(a); db.session.commit(); flash('Block removed.', 'success')
    return redirect(url_for('availability'))

@app.route('/schedules')
@login_required
def schedules():
    all_scheds = Schedule.query.order_by(Schedule.day, Schedule.start_time).all()
    statuses = {}
    for s in all_scheds:
        if s.is_pending: statuses[s.id] = ('pending', []); continue
        new = {'day': s.day, 'start_time': s.start_time, 'end_time': s.end_time, 'room_id': s.room_id, 'faculty_id': s.faculty_id, 'section_id': s.section_id, 'course_id': s.course_id}
        msgs = check_schedule_conflicts(new, all_scheds, exclude_id=s.id) + check_room_suitability(s.room, s.section, s.course)
        statuses[s.id] = ('ok' if not msgs else 'conflict', msgs)
    return render_template('schedules.html', schedules=all_scheds, statuses=statuses, terms=Term.query.all(), courses=Course.query.order_by(Course.code).all(), faculty=Faculty.query.order_by(Faculty.name).all(), sections=Section.query.order_by(Section.name).all(), rooms=Room.query.order_by(Room.code).all(), days=DAYS)

@app.route('/schedules/add', methods=['POST'])
@login_required
def add_schedule():
    try: term_id, course_id, faculty_id, section_id = int(request.form['term_id']), int(request.form['course_id']), int(request.form['faculty_id']), int(request.form['section_id'])
    except (KeyError, ValueError): flash('Select term, course, faculty, and section.', 'danger'); return redirect(url_for('schedules'))
    room_raw, day = request.form.get('room_id', '').strip(), request.form.get('day', '').strip() or None
    start, end = parse_time(request.form.get('start_time', '')), parse_time(request.form.get('end_time', ''))
    if room_raw and day and start and end:
        if start >= end: flash('Start must be before end.', 'danger'); return redirect(url_for('schedules'))
        new = {'day': day, 'start_time': start, 'end_time': end, 'room_id': int(room_raw), 'faculty_id': faculty_id, 'section_id': section_id, 'course_id': course_id}
        conflicts = check_schedule_conflicts(new, Schedule.query.all()) + check_room_suitability(db.session.get(Room, int(room_raw)), db.session.get(Section, section_id), db.session.get(Course, course_id))
        if conflicts: flash(' | '.join(conflicts), 'danger'); return redirect(url_for('schedules'))
        db.session.add(Schedule(term_id=term_id, course_id=course_id, faculty_id=faculty_id, section_id=section_id, room_id=int(room_raw), day=day, start_time=start, end_time=end))
        db.session.commit(); flash('Schedule added.', 'success'); return redirect(url_for('schedules'))
    db.session.add(Schedule(term_id=term_id, course_id=course_id, faculty_id=faculty_id, section_id=section_id))
    db.session.commit(); flash('Pending schedule added.', 'info'); return redirect(url_for('schedules'))

@app.route('/schedules/<int:id>/assign', methods=['POST'])
@login_required
def assign_schedule(id):
    s = db.session.get(Schedule, id)
    if not s: flash('Schedule not found.', 'danger'); return redirect(url_for('schedules'))
    room_id, day = int(request.form['room_id']), request.form['day']
    start, end = parse_time(request.form['start_time']), parse_time(request.form['end_time'])
    if not day or not start or not end or start >= end: flash('Invalid day or time.', 'danger'); return redirect(url_for('schedules'))
    new = {'day': day, 'start_time': start, 'end_time': end, 'room_id': room_id, 'faculty_id': s.faculty_id, 'section_id': s.section_id, 'course_id': s.course_id}
    conflicts = check_schedule_conflicts(new, Schedule.query.all(), exclude_id=s.id) + check_room_suitability(db.session.get(Room, room_id), s.section, s.course)
    if conflicts: flash(' | '.join(conflicts), 'danger'); return redirect(url_for('schedules'))
    s.room_id, s.day, s.start_time, s.end_time = room_id, day, start, end
    db.session.commit(); flash('Schedule assigned.', 'success'); return redirect(url_for('schedules'))

@app.route('/schedules/<int:id>/delete', methods=['POST'])
@login_required
def delete_schedule(id):
    s = db.session.get(Schedule, id)
    if s: db.session.delete(s); db.session.commit(); flash('Schedule deleted.', 'success')
    return redirect(url_for('schedules'))

@app.route('/schedules/clear', methods=['POST'])
@login_required
def clear_schedules():
    Schedule.query.delete(); db.session.commit(); flash('All schedules cleared.', 'success'); return redirect(url_for('schedules'))

@app.route('/conflicts')
@login_required
def conflicts():
    all_scheds = Schedule.query.all(); rows = []
    for s in [x for x in all_scheds if not x.is_pending]:
        new = {'day': s.day, 'start_time': s.start_time, 'end_time': s.end_time, 'room_id': s.room_id, 'faculty_id': s.faculty_id, 'section_id': s.section_id, 'course_id': s.course_id}
        rows.append({'schedule': s, 'messages': check_schedule_conflicts(new, all_scheds, exclude_id=s.id) + check_room_suitability(s.room, s.section, s.course)})
    return render_template('conflicts.html', rows=rows, total=len(rows))

@app.route('/generate', methods=['POST'])
@login_required
def generate():
    term = Term.query.first()
    if not term: flash('Create a term first.', 'danger'); return redirect(url_for('schedules'))
    assigned, unassigned = auto_generate(term.id)
    if assigned: flash(f'Auto-generator assigned {assigned} schedule(s).', 'success')
    if unassigned: flash(f"Could not place: {', '.join(f'{s.course.code}/{s.section.name}' for s in unassigned)}", 'warning')
    if not assigned and not unassigned: flash('No pending schedules to generate.', 'info')
    return redirect(url_for('schedules'))

@app.route('/reports')
@login_required
def reports():
    view, entity_id = request.args.get('view', ''), request.args.get('entity_id', type=int)
    term_id = request.args.get('term_id', type=int) or (Term.query.first().id if Term.query.first() else None)
    selected_scheds, title = [], 'Select a view'
    if view and entity_id and term_id:
        if view == 'section': selected_scheds = Schedule.query.filter_by(term_id=term_id, section_id=entity_id).all(); title = f"Timetable — Section {db.session.get(Section, entity_id).name}"
        elif view == 'faculty': selected_scheds = Schedule.query.filter_by(term_id=term_id, faculty_id=entity_id).all(); title = f"Timetable — {db.session.get(Faculty, entity_id).name}"
        elif view == 'room': selected_scheds = Schedule.query.filter_by(term_id=term_id, room_id=entity_id).all(); title = f"Timetable — Room {db.session.get(Room, entity_id).code}"
    grid = build_timetable(selected_scheds)
    room_util, faculty_load, pending = [], [], []
    if term_id:
        total_slots = len(DAYS) * len(TIME_SLOTS)
        for r in Room.query.all(): room_util.append({'room': r, 'used': Schedule.query.filter_by(term_id=term_id, room_id=r.id).count(), 'total': total_slots, 'pct': round((Schedule.query.filter_by(term_id=term_id, room_id=r.id).count() / total_slots) * 100, 1)})
        for f in Faculty.query.all(): faculty_load.append({'faculty': f, 'load': Schedule.query.filter_by(term_id=term_id, faculty_id=f.id).count()})
        pending = Schedule.query.filter_by(room_id=None).all()
    return render_template('reports.html', view=view, entity_id=entity_id, title=title, sections=Section.query.all(), faculty=Faculty.query.all(), rooms=Room.query.all(), terms=Term.query.all(), term_id=term_id, grid=grid, days=DAYS, time_slots=TIME_SLOTS, room_util=room_util, faculty_load=faculty_load, pending=pending)

if __name__ == '__main__':
    with app.app_context(): db.create_all()
    app.run(debug=True)
''',

    "seed.py": r'''import os
from datetime import time
from app import app, db, Term, Course, Faculty, Room, Section, Availability, Schedule, User
from werkzeug.security import generate_password_hash

def seed(admin_password):
    with app.app_context():
        db.create_all()
        
        if not User.query.filter_by(username="admin").first():
            db.session.add(User(username="admin", password_hash=generate_password_hash(admin_password), role="Admin"))
            db.session.commit()
            print("Administrator account created for username: admin")

        if Term.query.first(): return

        term = Term(name="1st Semester 2026 - 2027")
        db.session.add(term)
        db.session.add_all([
            Course(code="CSST 102", title="Machine Learning", units=3, room_type="lecture"),
            Course(code="CMSC 308", title="Programming Languages", units=3, room_type="lecture"),
            Course(code="CMSC 201", title="Data Structures", units=3, room_type="lab"),
            Faculty(name="Rolan Sotomayor", department="CCS"),
            Faculty(name="Maria Cruz", department="CCS"),
            Faculty(name="Juan Reyes", department="Math"),
            Room(code="Room 206", capacity=40, room_type="lecture"),
            Room(code="MAC LAB", capacity=30, room_type="lab"),
            Room(code="TESOL", capacity=38, room_type="lecture"),
            Section(name="BSCS 3A", program="BS Computer Science", size=35),
            Section(name="BSCS 3B", program="BS Computer Science", size=30),
            Section(name="BSIT 2A", program="BS Information Technology", size=40),
        ])
        db.session.commit()
        
        cruz = Faculty.query.filter_by(name="Maria Cruz").first()
        reyes = Faculty.query.filter_by(name="Juan Reyes").first()
        lab1 = Room.query.filter_by(code="MAC LAB").first()
        db.session.add_all([
            Availability(faculty_id=cruz.id, day="Mon", start_time=time(7, 0), end_time=time(9, 0)),
            Availability(faculty_id=reyes.id, day="Fri", start_time=time(15, 0), end_time=time(17, 0)),
            Availability(room_id=lab1.id, day="Wed", start_time=time(13, 0), end_time=time(15, 0)),
        ])
        
        csst102 = Course.query.filter_by(code="CSST 102").first()
        cmsc308 = Course.query.filter_by(code="CMSC 308").first()
        cmsc201 = Course.query.filter_by(code="CMSC 201").first()
        bscs3a = Section.query.filter_by(name="BSCS 3A").first()
        bscs3b = Section.query.filter_by(name="BSCS 3B").first()
        bsit2a = Section.query.filter_by(name="BSIT 2A").first()
        rolly = Faculty.query.filter_by(name="Rolan Sotomayor").first()
        r206 = Room.query.filter_by(code="Room 206").first()
        maclab = Room.query.filter_by(code="MAC LAB").first()

        db.session.add_all([
            Schedule(term_id=term.id, course_id=csst102.id, faculty_id=cruz.id, section_id=bscs3b.id, room_id=r206.id, day="Thu", start_time=time(7, 0), end_time=time(9, 0)),
            Schedule(term_id=term.id, course_id=cmsc308.id, faculty_id=rolly.id, section_id=bscs3a.id, room_id=r206.id, day="Thu", start_time=time(11, 0), end_time=time(13, 0)),
            Schedule(term_id=term.id, course_id=cmsc201.id, faculty_id=rolly.id, section_id=bsit2a.id, room_id=maclab.id, day="Thu", start_time=time(9, 0), end_time=time(11, 0)),
        ])
        db.session.commit()
        print("Database generated successfully with sample schedules!")

if __name__ == '__main__':
    admin_password = os.environ.get('SEED_ADMIN_PASSWORD')
    if not admin_password:
        raise SystemExit('Set SEED_ADMIN_PASSWORD to a temporary strong password before seeding.')
    seed(admin_password)
''',

    "templates/base.html": r'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>LSPU Timetable System</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.10.5/font/bootstrap-icons.css">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="{{ url_for('static', filename='style.css') }}">
</head>
<body>
{% if current_user.is_authenticated %}
<div class="d-flex">
    <!-- Sidebar -->
    <div class="sidebar p-3 d-flex flex-column">
        <div class="text-center mb-4 mt-2">
            <h4 class="text-white fw-bold"><span class="text-orange">LSPU</span> <span class="text-purple">Sync.</span></h4>
        </div>
        
        <div class="user-profile text-center mb-4">
            <div class="avatar mx-auto mb-2"><i class="bi bi-person-fill"></i></div>
            <h6 class="text-white mb-0">{{ current_user.username }}</h6>
            <small class="text-light opacity-75">{{ current_user.role }}</small>
        </div>

        <ul class="nav flex-column mb-auto">
            <li class="nav-item"><a class="nav-link text-white" href="{{ url_for('index') }}"><i class="bi bi-calendar-week me-2"></i> My Schedule</a></li>
            <li class="nav-item"><a class="nav-link text-white" href="{{ url_for('schedules') }}"><i class="bi bi-plus-square me-2"></i> Create Schedule</a></li>
            <li class="nav-item"><a class="nav-link text-white" href="{{ url_for('availability') }}"><i class="bi bi-display me-2"></i> Room Availability</a></li>
            <li class="nav-item"><a class="nav-link text-white" href="{{ url_for('reports') }}"><i class="bi bi-file-earmark-arrow-down me-2"></i> Export</a></li>
            
            <li class="nav-item mt-4"><hr class="text-light opacity-25"></li>
            <li class="nav-item"><a class="nav-link text-white" href="{{ url_for('academic') }}"><i class="bi bi-database me-2"></i> Master Data</a></li>
            <li class="nav-item"><a class="nav-link text-white" href="{{ url_for('conflicts') }}"><i class="bi bi-exclamation-triangle me-2"></i> Conflicts</a></li>
        </ul>
        <hr class="text-light">
        <a class="nav-link text-white mb-3" href="{{ url_for('logout') }}"><i class="bi bi-box-arrow-right me-2"></i> Logout</a>
    </div>

    <!-- Main Content -->
    <div class="main-content w-100">
        <!-- Topbar -->
        <div class="topbar px-4 py-3 d-flex justify-content-between align-items-center">
            <h5 class="mb-0 text-white fw-normal">Hello, <strong>{{ current_user.username }}</strong></h5>
            <div class="d-flex align-items-center text-white">
                <span class="me-3 small">College of Computer Studies<br>Laguna State Polytechnic University</span>
                <div class="bg-white rounded-circle p-2" style="width: 45px; height: 45px; display:flex; align-items:center; justify-content:center;">
                    <i class="bi bi-building text-dark fs-4"></i>
                </div>
            </div>
        </div>
        
        <div class="container-fluid p-4">
            {% with messages = get_flashed_messages(with_categories=true) %}
                {% if messages %}
                    {% for cat, msg in messages %}
                        <div class="alert alert-{{ 'danger' if cat == 'danger' else ('success' if cat == 'success' else ('warning' if cat == 'warning' else 'info')) }} alert-dismissible fade show shadow-sm">
                            {{ msg }}
                            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
                        </div>
                    {% endfor %}
                {% endif %}
            {% endwith %}
            {% block content %}{% endblock %}
        </div>
    </div>
</div>
{% else %}
    <!-- Auth Layout -->
    {% block auth_content %}{% endblock %}
{% endif %}
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>''',

    "templates/login.html": r'''{% extends 'base.html' %}
{% block auth_content %}
<div class="auth-wrapper">
    <div class="row g-0 h-100">
        <div class="col-md-6 d-none d-md-flex flex-column justify-content-center align-items-center text-white p-5" style="background: linear-gradient(135deg, #2b0f3c 0%, #1a0826 100%);">
            <h1 class="display-4 fw-bold mb-4" style="line-height: 1.2;">Manage Syncing<br>Your <span class="text-orange">College</span><br><span class="text-purple">Class Schedule</span></h1>
            <h1 class="display-3 fw-bold mt-4"><span class="text-orange">LSPU</span> <span class="text-purple">Sync.</span></h1>
        </div>
        <div class="col-md-6 d-flex align-items-center justify-content-center auth-bg">
            <div class="glass-card p-5 w-100" style="max-width: 450px;">
                <h3 class="text-white text-center mb-4 fw-bold">Login</h3>
                <form method="POST">
                    <div class="mb-3">
                        <input type="text" name="username" class="form-control glass-input" placeholder="Email or Username" required>
                    </div>
                    <div class="mb-4">
                        <input type="password" name="password" class="form-control glass-input" placeholder="Password" required>
                    </div>
                    <button type="submit" class="btn btn-dark w-100 rounded-pill py-2 fw-bold">Login</button>
                </form>
                <div class="text-center mt-4">
                    <small class="text-light opacity-75">Haven't created an account? <a href="{{ url_for('register') }}" class="text-orange text-decoration-none fw-bold">Signup</a></small>
                </div>
            </div>
        </div>
    </div>
</div>
{% endblock %}''',

    "templates/register.html": r'''{% extends 'base.html' %}
{% block auth_content %}
<div class="auth-wrapper">
    <div class="row g-0 h-100">
        <div class="col-md-6 d-none d-md-flex flex-column justify-content-center align-items-center text-white p-5" style="background: linear-gradient(135deg, #2b0f3c 0%, #1a0826 100%);">
            <h1 class="display-4 fw-bold mb-4" style="line-height: 1.2;">Manage Syncing<br>Your <span class="text-orange">College</span><br><span class="text-purple">Class Schedule</span></h1>
            <h1 class="display-3 fw-bold mt-4"><span class="text-orange">LSPU</span> <span class="text-purple">Sync.</span></h1>
        </div>
        <div class="col-md-6 d-flex align-items-center justify-content-center auth-bg">
            <div class="glass-card p-5 w-100" style="max-width: 450px;">
                <h3 class="text-white text-center mb-4 fw-bold">Sign Up</h3>
                <form method="POST">
                    <div class="mb-3">
                        <input type="text" name="username" class="form-control glass-input" placeholder="Username" required>
                    </div>
                    <div class="mb-4">
                        <input type="password" name="password" class="form-control glass-input" placeholder="Password" required>
                    </div>
                    <button type="submit" class="btn btn-dark w-100 rounded-pill py-2 fw-bold">Sign Up</button>
                </form>
                <div class="text-center mt-4">
                    <small class="text-light opacity-75">Already have an account? <a href="{{ url_for('login') }}" class="text-orange text-decoration-none fw-bold">Login</a></small>
                </div>
            </div>
        </div>
    </div>
</div>
{% endblock %}''',

    "templates/index.html": r'''{% extends 'base.html' %}
{% block content %}
<div class="d-flex justify-content-between align-items-center mb-3">
    <div>
        <h2 class="fw-bold mb-0" style="color: #310742;">My Schedule</h2>
        <p class="text-muted small mb-0 fst-italic">1st Semester 2026 - 2027</p>
    </div>
</div>

<div class="row g-3 mb-4">
    <div class="col-md-4">
        <div class="card custom-card h-100 p-3 border-purple">
            <div class="card-body">
                <h6 class="text-dark fw-bold mb-1">Classes this week</h6>
                <h1 class="display-4 fw-bold mb-0 text-purple">{{ stats.schedules }}</h1>
            </div>
        </div>
    </div>
    <div class="col-md-4">
        <div class="card custom-card h-100 p-3 border-purple">
            <div class="card-body">
                <h6 class="text-dark fw-bold mb-1">Total Faculty</h6>
                <h1 class="display-4 fw-bold mb-0 text-purple">{{ stats.faculty }}</h1>
            </div>
        </div>
    </div>
    <div class="col-md-4">
        <div class="card custom-card h-100 p-3 bg-orange-subtle border-orange">
            <div class="card-body">
                <h6 class="text-dark fw-bold mb-1">Needs attention</h6>
                <h1 class="display-4 fw-bold mb-0 text-orange">{{ stats.pending }} pending</h1>
            </div>
        </div>
    </div>
</div>

<div class="card custom-card p-4">
    <div class="table-responsive">
        <table class="table table-borderless custom-timetable mb-0">
            <thead>
                <tr>
                    <th style="width: 80px;"></th>
                    {% for d in days %}<th>{{ d }}</th>{% endfor %}
                </tr>
            </thead>
            <tbody>
            {% for start, end in time_slots %}
            <tr>
                <td class="fw-bold text-muted small text-center align-middle">{{ start.strftime('%I:%M %p').lstrip('0') }}</td>
                {% for d in days %}
                    {% set cell = grid.get((d, start.strftime('%H:%M'))) %}
                    <td class="p-1 position-relative">
                        {% if cell %}
                        <div class="schedule-block">
                            <div class="fw-bold">{{ cell.course.code }}</div>
                            <div class="small">{{ cell.section.name }}</div>
                        </div>
                        {% else %}
                        <div class="empty-slot"></div>
                        {% endif %}
                    </td>
                {% endfor %}
            </tr>
            {% endfor %}
            </tbody>
        </table>
    </div>
</div>
{% endblock %}''',

    "templates/academic.html": r'''{% extends 'base.html' %}
{% block content %}
<h2 class="fw-bold mb-4" style="color: #310742;">Master Data Management</h2>
<ul class="nav nav-pills mb-4 custom-tabs" id="pills-tab" role="tablist">
    <li class="nav-item"><button class="nav-link active" data-bs-toggle="pill" data-bs-target="#tab-courses">Courses</button></li>
    <li class="nav-item"><button class="nav-link" data-bs-toggle="pill" data-bs-target="#tab-faculty">Faculty</button></li>
    <li class="nav-item"><button class="nav-link" data-bs-toggle="pill" data-bs-target="#tab-rooms">Rooms</button></li>
    <li class="nav-item"><button class="nav-link" data-bs-toggle="pill" data-bs-target="#tab-sections">Sections</button></li>
    <li class="nav-item"><button class="nav-link" data-bs-toggle="pill" data-bs-target="#tab-terms">Terms</button></li>
</ul>

<div class="tab-content custom-tab-content card custom-card p-4">
    <div class="tab-pane fade show active" id="tab-courses">
        <form method="POST" action="{{ url_for('add_course') }}" class="row g-2 mb-4">
            <div class="col-md-2"><input name="code" class="form-control" placeholder="Code (CS101)" required></div>
            <div class="col-md-4"><input name="title" class="form-control" placeholder="Title" required></div>
            <div class="col-md-2"><input name="units" type="number" min="1" value="3" class="form-control"></div>
            <div class="col-md-2"><select name="room_type" class="form-select"><option value="lecture">Lecture</option><option value="lab">Lab</option></select></div>
            <div class="col-md-2"><button class="btn btn-purple w-100">Add Course</button></div>
        </form>
        <table class="table custom-table">
            <thead><tr><th>Code</th><th>Title</th><th>Units</th><th>Type</th><th></th></tr></thead>
            <tbody>{% for c in courses %}<tr><td class="fw-bold">{{ c.code }}</td><td>{{ c.title }}</td><td>{{ c.units }}</td><td>{{ c.room_type }}</td><td class="text-end"><form method="POST" action="{{ url_for('delete_course', id=c.id) }}" onsubmit="return confirm('Delete course?')"><button class="btn btn-sm btn-outline-danger"><i class="bi bi-trash"></i></button></form></td></tr>{% endfor %}</tbody>
        </table>
    </div>

    <div class="tab-pane fade" id="tab-faculty">
        <form method="POST" action="{{ url_for('add_faculty') }}" class="row g-2 mb-4">
            <div class="col-md-5"><input name="name" class="form-control" placeholder="Full name" required></div>
            <div class="col-md-5"><input name="department" class="form-control" placeholder="Department"></div>
            <div class="col-md-2"><button class="btn btn-purple w-100">Add Faculty</button></div>
        </form>
        <table class="table custom-table">
            <thead><tr><th>Name</th><th>Department</th><th></th></tr></thead>
            <tbody>{% for f in faculty %}<tr><td class="fw-bold">{{ f.name }}</td><td>{{ f.department }}</td><td class="text-end"><form method="POST" action="{{ url_for('delete_faculty', id=f.id) }}" onsubmit="return confirm('Delete faculty?')"><button class="btn btn-sm btn-outline-danger"><i class="bi bi-trash"></i></button></form></td></tr>{% endfor %}</tbody>
        </table>
    </div>

    <div class="tab-pane fade" id="tab-rooms">
        <form method="POST" action="{{ url_for('add_room') }}" class="row g-2 mb-4">
            <div class="col-md-3"><input name="code" class="form-control" placeholder="Code (Room 206)" required></div>
            <div class="col-md-3"><input name="capacity" type="number" min="1" value="30" class="form-control"></div>
            <div class="col-md-3"><select name="room_type" class="form-select"><option value="lecture">Lecture</option><option value="lab">Lab</option></select></div>
            <div class="col-md-3"><button class="btn btn-purple w-100">Add Room</button></div>
        </form>
        <table class="table custom-table">
            <thead><tr><th>Code</th><th>Capacity</th><th>Type</th><th></th></tr></thead>
            <tbody>{% for r in rooms %}<tr><td class="fw-bold">{{ r.code }}</td><td>{{ r.capacity }}</td><td>{{ r.room_type }}</td><td class="text-end"><form method="POST" action="{{ url_for('delete_room', id=r.id) }}" onsubmit="return confirm('Delete room?')"><button class="btn btn-sm btn-outline-danger"><i class="bi bi-trash"></i></button></form></td></tr>{% endfor %}</tbody>
        </table>
    </div>

    <div class="tab-pane fade" id="tab-sections">
        <form method="POST" action="{{ url_for('add_section') }}" class="row g-2 mb-4">
            <div class="col-md-4"><input name="name" class="form-control" placeholder="Name (BSCS 3A)" required></div>
            <div class="col-md-4"><input name="program" class="form-control" placeholder="Program"></div>
            <div class="col-md-2"><input name="size" type="number" min="1" value="30" class="form-control"></div>
            <div class="col-md-2"><button class="btn btn-purple w-100">Add Section</button></div>
        </form>
        <table class="table custom-table">
            <thead><tr><th>Name</th><th>Program</th><th>Size</th><th></th></tr></thead>
            <tbody>{% for s in sections %}<tr><td class="fw-bold">{{ s.name }}</td><td>{{ s.program }}</td><td>{{ s.size }}</td><td class="text-end"><form method="POST" action="{{ url_for('delete_section', id=s.id) }}" onsubmit="return confirm('Delete section?')"><button class="btn btn-sm btn-outline-danger"><i class="bi bi-trash"></i></button></form></td></tr>{% endfor %}</tbody>
        </table>
    </div>

    <div class="tab-pane fade" id="tab-terms">
        <form method="POST" action="{{ url_for('add_term') }}" class="row g-2 mb-4">
            <div class="col-md-9"><input name="name" class="form-control" placeholder="Term name (e.g. 1st Semester 2026-2027)" required></div>
            <div class="col-md-3"><button class="btn btn-purple w-100">Add Term</button></div>
        </form>
        <table class="table custom-table">
            <thead><tr><th>Name</th><th></th></tr></thead>
            <tbody>{% for t in terms %}<tr><td class="fw-bold">{{ t.name }}</td><td class="text-end"><form method="POST" action="{{ url_for('delete_term', id=t.id) }}" onsubmit="return confirm('Delete term?')"><button class="btn btn-sm btn-outline-danger"><i class="bi bi-trash"></i></button></form></td></tr>{% endfor %}</tbody>
        </table>
    </div>
</div>
{% endblock %}''',

    "templates/availability.html": r'''{% extends 'base.html' %}
{% block content %}
<h2 class="fw-bold mb-4" style="color: #310742;">Room & Faculty Availability</h2>
<div class="row g-4">
    <div class="col-lg-4">
        <div class="card custom-card p-4">
            <h5 class="fw-bold mb-3" style="color: #310742;">Add Unavailability</h5>
            <form method="POST" action="{{ url_for('add_availability') }}">
                <div class="mb-3">
                    <label class="form-label small fw-bold text-muted">Select Entity</label>
                    <select name="entity" class="form-select" required>
                        <option value="">— Select faculty or room —</option>
                        <optgroup label="Faculty">{% for f in faculty %}<option value="faculty:{{ f.id }}">{{ f.name }}</option>{% endfor %}</optgroup>
                        <optgroup label="Rooms">{% for r in rooms %}<option value="room:{{ r.id }}">{{ r.code }}</option>{% endfor %}</optgroup>
                    </select>
                </div>
                <div class="mb-3">
                    <label class="form-label small fw-bold text-muted">Day</label>
                    <select name="day" class="form-select" required>{% for d in days %}<option value="{{ d }}">{{ d }}</option>{% endfor %}</select>
                </div>
                <div class="row mb-4">
                    <div class="col-6"><label class="form-label small fw-bold text-muted">Start Time</label><input type="time" name="start_time" class="form-control" required></div>
                    <div class="col-6"><label class="form-label small fw-bold text-muted">End Time</label><input type="time" name="end_time" class="form-control" required></div>
                </div>
                <button class="btn btn-purple w-100">Add Block</button>
            </form>
        </div>
    </div>
    <div class="col-lg-8">
        <div class="card custom-card p-4 h-100">
            <h5 class="fw-bold mb-3" style="color: #310742;">Existing Blocks</h5>
            <div class="table-responsive">
                <table class="table custom-table">
                    <thead><tr><th>Entity</th><th>Day</th><th>Time</th><th></th></tr></thead>
                    <tbody>
                    {% for a in availabilities %}
                    <tr>
                        <td>{% if a.faculty_id %}<span class="badge bg-secondary me-2">Faculty</span> {{ a.faculty.name }}{% elif a.room_id %}<span class="badge bg-warning text-dark me-2">Room</span> {{ a.room.code }}{% endif %}</td>
                        <td class="fw-bold">{{ a.day }}</td>
                        <td>{{ a.start_time.strftime('%I:%M %p') }} - {{ a.end_time.strftime('%I:%M %p') }}</td>
                        <td class="text-end"><form method="POST" action="{{ url_for('delete_availability', id=a.id) }}"><button class="btn btn-sm btn-outline-danger">Remove</button></form></td>
                    </tr>
                    {% else %}
                    <tr><td colspan="4" class="text-center text-muted py-4">No blocks set.</td></tr>
                    {% endfor %}
                    </tbody>
                </table>
            </div>
        </div>
    </div>
</div>
{% endblock %}''',

    "templates/schedules.html": r'''{% extends 'base.html' %}
{% block content %}
<div class="d-flex justify-content-between align-items-center mb-4">
    <h2 class="fw-bold mb-0" style="color: #310742;">Create Schedule</h2>
    <div>
        <form method="POST" action="{{ url_for('generate') }}" class="d-inline"><button class="btn btn-orange">⚙ Auto-Generate</button></form>
        <form method="POST" action="{{ url_for('clear_schedules') }}" class="d-inline" onsubmit="return confirm('Clear ALL schedules?')"><button class="btn btn-outline-danger">Clear All</button></form>
    </div>
</div>

<div class="card custom-card p-4 mb-4">
    <form method="POST" action="{{ url_for('add_schedule') }}" class="row g-3 align-items-end">
        <div class="col-md-3">
            <label class="form-label small fw-bold text-muted">Course</label>
            <select name="course_id" class="form-select" required>{% for c in courses %}<option value="{{ c.id }}">{{ c.code }} — {{ c.title }}</option>{% endfor %}</select>
        </div>
        <div class="col-md-3">
            <label class="form-label small fw-bold text-muted">Faculty</label>
            <select name="faculty_id" class="form-select" required>{% for f in faculty %}<option value="{{ f.id }}">{{ f.name }}</option>{% endfor %}</select>
        </div>
        <div class="col-md-3">
            <label class="form-label small fw-bold text-muted">Section</label>
            <select name="section_id" class="form-select" required>{% for s in sections %}<option value="{{ s.id }}">{{ s.name }}</option>{% endfor %}</select>
        </div>
        <div class="col-md-3">
            <label class="form-label small fw-bold text-muted">Room (Optional)</label>
            <select name="room_id" class="form-select"><option value="">— Pending —</option>{% for r in rooms %}<option value="{{ r.id }}">{{ r.code }}</option>{% endfor %}</select>
        </div>
        
        <div class="col-md-2">
            <label class="form-label small fw-bold text-muted">Day</label>
            <select name="day" class="form-select"><option value="">—</option>{% for d in days %}<option value="{{ d }}">{{ d }}</option>{% endfor %}</select>
        </div>
        <div class="col-md-2">
            <label class="form-label small fw-bold text-muted">Start Time</label>
            <input type="time" name="start_time" class="form-control">
        </div>
        <div class="col-md-2">
            <label class="form-label small fw-bold text-muted">End Time</label>
            <input type="time" name="end_time" class="form-control">
        </div>
        <div class="col-md-3">
            <label class="form-label small fw-bold text-muted">Term</label>
            <select name="term_id" class="form-select" required>{% for t in terms %}<option value="{{ t.id }}">{{ t.name }}</option>{% endfor %}</select>
        </div>
        <div class="col-md-3">
            <button class="btn btn-purple w-100">Add Schedule</button>
        </div>
    </form>
</div>

<div class="card custom-card p-4">
    <div class="table-responsive">
        <table class="table custom-table align-middle">
            <thead><tr><th>Course</th><th>Faculty</th><th>Section</th><th>Room</th><th>Day</th><th>Time</th><th>Status</th><th></th></tr></thead>
            <tbody>
            {% for s in schedules %}
                {% set status, messages = statuses[s.id] %}
                <tr>
                    <td><strong>{{ s.course.code }}</strong><br><small class="text-muted">{{ s.course.title }}</small></td>
                    <td>{{ s.faculty.name }}</td>
                    <td>{{ s.section.name }}</td>
                    <td>{% if s.room %}{{ s.room.code }}{% else %}<span class="text-muted">—</span>{% endif %}</td>
                    <td>{{ s.day or '—' }}</td>
                    <td>{% if s.start_time %}{{ s.start_time.strftime('%I:%M %p') }} - {{ s.end_time.strftime('%I:%M %p') }}{% else %}—{% endif %}</td>
                    <td>
                        {% if status == 'conflict' %}<span class="badge bg-danger mb-1">Conflict</span><div class="small text-danger">{% for m in messages %}<div>• {{ m }}</div>{% endfor %}</div>
                        {% elif status == 'pending' %}<span class="badge bg-warning text-dark">Pending</span>
                        {% else %}<span class="badge bg-success">Approved</span>{% endif %}
                    </td>
                    <td class="text-end">
                        {% if s.is_pending %}<button class="btn btn-sm btn-outline-primary" data-bs-toggle="modal" data-bs-target="#assign{{ s.id }}">Assign</button>{% endif %}
                        <form method="POST" action="{{ url_for('delete_schedule', id=s.id) }}" class="d-inline" onsubmit="return confirm('Delete?')"><button class="btn btn-sm btn-outline-danger"><i class="bi bi-trash"></i></button></form>
                    </td>
                </tr>

                {% if s.is_pending %}
                <div class="modal fade" id="assign{{ s.id }}" tabindex="-1">
                    <div class="modal-dialog">
                        <div class="modal-content">
                            <form method="POST" action="{{ url_for('assign_schedule', id=s.id) }}">
                                <div class="modal-header"><h5 class="modal-title">Assign Room & Time</h5><button type="button" class="btn-close" data-bs-dismiss="modal"></button></div>
                                <div class="modal-body">
                                    <div class="mb-3"><label class="form-label fw-bold">Room</label><select name="room_id" class="form-select" required>{% for r in rooms %}<option value="{{ r.id }}">{{ r.code }} (Cap: {{ r.capacity }})</option>{% endfor %}</select></div>
                                    <div class="mb-3"><label class="form-label fw-bold">Day</label><select name="day" class="form-select" required>{% for d in days %}<option value="{{ d }}">{{ d }}</option>{% endfor %}</select></div>
                                    <div class="row"><div class="col-6"><label class="form-label fw-bold">Start</label><input type="time" name="start_time" class="form-control" required></div><div class="col-6"><label class="form-label fw-bold">End</label><input type="time" name="end_time" class="form-control" required></div></div>
                                </div>
                                <div class="modal-footer"><button class="btn btn-purple">Save</button></div>
                            </form>
                        </div>
                    </div>
                </div>
                {% endif %}
            {% endfor %}
            </tbody>
        </table>
    </div>
</div>
{% endblock %}''',

    "templates/conflicts.html": r'''{% extends 'base.html' %}
{% block content %}
<h2 class="fw-bold mb-4" style="color: #310742;">Live Conflict Detection</h2>
<div class="mb-4">
    <span class="badge bg-success fs-6 me-2">{{ total - rows|selectattr('messages')|list|length }} Approved</span>
    <span class="badge bg-danger fs-6">{{ rows|selectattr('messages')|list|length }} Conflicts</span>
</div>

<div class="row g-4">
    {% for row in rows %}
    <div class="col-lg-6">
        <div class="card custom-card h-100 border-0 {% if row.messages %}bg-danger-subtle{% endif %}">
            <div class="card-body">
                <div class="d-flex justify-content-between align-items-center mb-3">
                    <h5 class="fw-bold mb-0">{{ row.schedule.course.code }} <span class="text-muted fw-normal">({{ row.schedule.section.name }})</span></h5>
                    {% if row.messages %}<span class="badge bg-danger">Conflict</span>{% else %}<span class="badge bg-success">OK</span>{% endif %}
                </div>
                <div class="row small mb-3">
                    <div class="col-6"><strong>Faculty:</strong> {{ row.schedule.faculty.name }}</div>
                    <div class="col-6"><strong>Room:</strong> {{ row.schedule.room.code }}</div>
                    <div class="col-12 mt-1"><strong>Time:</strong> {{ row.schedule.day }} {{ row.schedule.start_time.strftime('%I:%M %p') }} - {{ row.schedule.end_time.strftime('%I:%M %p') }}</div>
                </div>
                {% if row.messages %}
                <div class="alert alert-danger mb-0 py-2">
                    <ul class="mb-0 ps-3">{% for m in row.messages %}<li>{{ m }}</li>{% endfor %}</ul>
                </div>
                {% endif %}
            </div>
        </div>
    </div>
    {% endfor %}
</div>
{% endblock %}''',

    "templates/reports.html": r'''{% extends 'base.html' %}
{% block content %}
<h2 class="fw-bold mb-4" style="color: #310742;">Export & Reports</h2>

<div class="card custom-card p-3 mb-4">
    <form method="GET" class="row g-2 align-items-end">
        <div class="col-md-3"><label class="form-label small fw-bold text-muted">Term</label><select name="term_id" class="form-select">{% for t in terms %}<option value="{{ t.id }}" {% if t.id == term_id %}selected{% endif %}>{{ t.name }}</option>{% endfor %}</select></div>
        <div class="col-md-3"><label class="form-label small fw-bold text-muted">View Mode</label><select name="view" class="form-select"><option value="section" {% if view == 'section' %}selected{% endif %}>By Section</option><option value="faculty" {% if view == 'faculty' %}selected{% endif %}>By Faculty</option><option value="room" {% if view == 'room' %}selected{% endif %}>By Room</option></select></div>
        <div class="col-md-4">
            <label class="form-label small fw-bold text-muted">Filter</label>
            <select name="entity_id" class="form-select">
                {% if view == 'faculty' %}{% for f in faculty %}<option value="{{ f.id }}" {% if f.id == entity_id %}selected{% endif %}>{{ f.name }}</option>{% endfor %}
                {% elif view == 'room' %}{% for r in rooms %}<option value="{{ r.id }}" {% if r.id == entity_id %}selected{% endif %}>{{ r.code }}</option>{% endfor %}
                {% else %}{% for s in sections %}<option value="{{ s.id }}" {% if s.id == entity_id %}selected{% endif %}>{{ s.name }}</option>{% endfor %}{% endif %}
            </select>
        </div>
        <div class="col-md-2"><button class="btn btn-purple w-100">Generate</button></div>
    </form>
</div>

<div class="card custom-card p-4 mb-4">
    <h4 class="fw-bold mb-4" style="color: #310742;">{{ title }}</h4>
    <div class="table-responsive">
        <table class="table table-borderless custom-timetable mb-0">
            <thead>
                <tr>
                    <th style="width: 80px;"></th>
                    {% for d in days %}<th>{{ d }}</th>{% endfor %}
                </tr>
            </thead>
            <tbody>
            {% for start, end in time_slots %}
            <tr>
                <td class="fw-bold text-muted small text-center align-middle">{{ start.strftime('%I:%M %p').lstrip('0') }}</td>
                {% for d in days %}
                    {% set cell = grid.get((d, start.strftime('%H:%M'))) %}
                    <td class="p-1 position-relative">
                        {% if cell %}
                        <div class="schedule-block">
                            <div class="fw-bold">{{ cell.course.code }}</div>
                            <div class="small">{{ cell.section.name }}</div>
                        </div>
                        {% else %}
                        <div class="empty-slot"></div>
                        {% endif %}
                    </td>
                {% endfor %}
            </tr>
            {% endfor %}
            </tbody>
        </table>
    </div>
</div>

<div class="row g-4">
    <div class="col-lg-6">
        <div class="card custom-card p-4 h-100">
            <h5 class="fw-bold mb-3" style="color: #310742;">Room Utilization</h5>
            <table class="table custom-table table-sm">
                <thead><tr><th>Room</th><th>Classes</th><th>Utilization</th></tr></thead>
                <tbody>{% for u in room_util %}<tr><td class="fw-bold">{{ u.room.code }}</td><td>{{ u.used }} / {{ u.total }}</td><td><div class="progress" style="height:10px;"><div class="progress-bar bg-purple" style="width: {{ u.pct }}%"></div></div></td></tr>{% endfor %}</tbody>
            </table>
        </div>
    </div>
    <div class="col-lg-6">
        <div class="card custom-card p-4 h-100">
            <h5 class="fw-bold mb-3" style="color: #310742;">Faculty Load</h5>
            <table class="table custom-table table-sm">
                <thead><tr><th>Instructor</th><th>Total Classes</th></tr></thead>
                <tbody>{% for f in faculty_load %}<tr><td class="fw-bold">{{ f.faculty.name }}</td><td><span class="badge bg-purple">{{ f.load }}</span></td></tr>{% endfor %}</tbody>
            </table>
        </div>
    </div>
</div>
{% endblock %}''',

    "static/style.css": r'''@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700&display=swap');

body { font-family: 'Inter', sans-serif; background-color: #f8f9fa; overflow-x: hidden; }
.text-orange { color: #ff6b00 !important; }
.text-purple { color: #62128a !important; }
.bg-purple { background-color: #62128a !important; }
.bg-orange-subtle { background-color: #fff3e0 !important; }
.border-orange { border: 1px solid #ff6b00 !important; }
.border-purple { border: 1px solid #62128a !important; }

/* Layout */
.d-flex { min-height: 100vh; }
.sidebar { width: 260px; background-color: #310742; position: fixed; height: 100vh; z-index: 1000; overflow-y: auto; }
.main-content { margin-left: 260px; background-color: #f8f9fa; min-height: 100vh; }
.topbar { background-color: #2b0f3c; }

/* Sidebar Elements */
.sidebar .nav-link { color: rgba(255,255,255,0.7); padding: 12px 20px; border-radius: 8px; margin-bottom: 5px; transition: 0.3s; font-weight: 600; font-size: 0.95rem; }
.sidebar .nav-link:hover, .sidebar .nav-link.active { color: #fff; background-color: rgba(255,255,255,0.1); }
.sidebar .nav-link i { font-size: 1.2rem; }
.avatar { width: 70px; height: 70px; background-color: #555; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 2rem; color: #fff; border: 3px solid #62128a; }

/* Auth Pages */
.auth-wrapper { height: 100vh; background: #1a0826; }
.auth-bg { background: linear-gradient(135deg, #62128a 0%, #2b0f3c 100%); }
.glass-card { background: rgba(255, 255, 255, 0.1); backdrop-filter: blur(10px); -webkit-backdrop-filter: blur(10px); border: 1px solid rgba(255, 255, 255, 0.2); border-radius: 20px; box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.3); }
.glass-input { background: rgba(255, 255, 255, 0.05) !important; border: 1px solid rgba(255, 255, 255, 0.5) !important; color: #fff !important; border-radius: 10px; padding: 12px 15px; }
.glass-input::placeholder { color: rgba(255, 255, 255, 0.6); }
.glass-input:focus { background: rgba(255, 255, 255, 0.15) !important; box-shadow: none; border-color: #ff6b00 !important; }

/* Custom Cards & Buttons */
.custom-card { background: #fff; border-radius: 15px; border: 1px solid rgba(98, 18, 138, 0.1); box-shadow: 0 4px 15px rgba(0,0,0,0.02); }
.btn-purple { background-color: #62128a; color: #fff; border-radius: 8px; font-weight: 600; }
.btn-purple:hover { background-color: #4a0b69; color: #fff; }
.btn-orange { background-color: #ff6b00; color: #fff; border-radius: 8px; font-weight: 600; border: none; }
.btn-orange:hover { background-color: #e65c00; color: #fff; }

/* Tables & Tabs */
.custom-tabs .nav-link { color: #6c757d; font-weight: 600; border-radius: 20px; padding: 8px 20px; margin-right: 10px; border: 1px solid #dee2e6; background: #fff; }
.custom-tabs .nav-link.active { background-color: #310742; color: #fff; border-color: #310742; }
.custom-table th { font-size: 0.85rem; text-transform: uppercase; letter-spacing: 0.5px; color: #6c757d; font-weight: 700; border-bottom: 2px solid #e9ecef; }
.custom-table td { vertical-align: middle; color: #333; border-bottom: 1px solid #e9ecef; }

/* Custom Dashboard Grid */
.custom-timetable { border-collapse: separate; border-spacing: 0 5px; }
.custom-timetable th { text-align: center; color: #000; font-weight: 700; border: none; padding-bottom: 15px; }
.custom-timetable td { border: none; padding: 2px !important; min-width: 120px; height: 50px; }
.empty-slot { width: 100%; height: 100%; border-bottom: 1px solid #e0d0e8; }
.schedule-block { background-color: #310742; color: #fff; padding: 10px; border-radius: 8px; height: 100%; display: flex; flex-direction: column; justify-content: center; box-shadow: 0 4px 6px rgba(49,7,66,0.3); }
'''
}


def harden_generated_files():
    """Keep regenerated scaffold files aligned with app security settings."""
    import re
    generated_app = FILES["app.py"]
    generated_app = generated_app.replace(
        "import os\nfrom datetime import time, datetime",
        "import os\nimport secrets\nfrom functools import wraps\nimport click\nfrom flask import abort\nfrom flask_wtf.csrf import CSRFProtect\nfrom datetime import time, datetime", 1)
    generated_app = generated_app.replace(
        "app = Flask(__name__)\napp.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY') or os.urandom(32)\n",
        """app = Flask(__name__)
APP_ENV = os.environ.get('APP_ENV', 'development').lower()
secret_key = os.environ.get('FLASK_SECRET_KEY')
if APP_ENV == 'production' and not secret_key:
    raise RuntimeError('FLASK_SECRET_KEY must be set when APP_ENV=production.')
app.config['SECRET_KEY'] = secret_key or secrets.token_hex(32)
app.config['DEBUG'] = APP_ENV == 'development' and os.environ.get('FLASK_DEBUG') == '1'
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = APP_ENV == 'production'
csrf = CSRFProtect(app)
""", 1)
    generated_app = generated_app.replace(
        "login_manager.login_message_category = 'warning'\n",
        """login_manager.login_message_category = 'warning'


def admin_required(view):
    @wraps(view)
    @login_required
    def wrapped_view(*args, **kwargs):
        if current_user.role != 'Admin':
            abort(403)
        return view(*args, **kwargs)
    return wrapped_view


@app.cli.command('init-db')
def init_db():
    db.create_all()
    click.echo('Database tables created.')


@app.cli.command('make-admin')
@click.argument('username')
def make_admin(username):
    user = User.query.filter_by(username=username).first()
    if user is None:
        raise click.ClickException(f'No account found for {username!r}.')
    user.role = 'Admin'
    db.session.commit()
    click.echo(f'{username} is now an administrator.')
""", 1)
    admin_functions = {'academic','add_course','delete_course','add_faculty','delete_faculty','add_room','delete_room','add_section','delete_section','add_term','delete_term','availability','add_availability','delete_availability','schedules','add_schedule','assign_schedule','delete_schedule','clear_schedules','generate'}
    for name in admin_functions:
        pattern = re.compile(r"(@app\.route\([^\n]+\)\n)@login_required\n(def " + re.escape(name) + r"\()")
        generated_app, count = pattern.subn(r"\1@admin_required\n\2", generated_app, count=1)
        if count != 1:
            raise RuntimeError(f'Could not secure generated route {name}')
    generated_app = generated_app.replace("@app.route('/logout')\n@login_required", "@app.route('/logout', methods=['POST'])\n@login_required")
    generated_app = generated_app.replace('app.run(debug=True)', "app.run(debug=app.config['DEBUG'])")
    FILES['app.py'] = generated_app
    form_pattern = re.compile(r"(<form\b[^>]*\bmethod\s*=\s*['\"]POST['\"][^>]*>)", re.IGNORECASE)
    for filename, content in list(FILES.items()):
        if filename.startswith('templates/') and filename.endswith('.html'):
            content = form_pattern.sub(r'\1\n<input type="hidden" name="csrf_token" value="{{ csrf_token() }}">', content)
            if filename == 'templates/base.html':
                content = content.replace(
                    '<li class="nav-item"><a class="nav-link text-white" href="{{ url_for(\'schedules\') }}"><i class="bi bi-plus-square me-2"></i> Create Schedule</a></li>\n            <li class="nav-item"><a class="nav-link text-white" href="{{ url_for(\'availability\') }}"><i class="bi bi-display me-2"></i> Room Availability</a></li>',
                    "{% if current_user.role == 'Admin' %}\n            <li class=\"nav-item\"><a class=\"nav-link text-white\" href=\"{{ url_for('schedules') }}\"><i class=\"bi bi-plus-square me-2\"></i> Create Schedule</a></li>\n            <li class=\"nav-item\"><a class=\"nav-link text-white\" href=\"{{ url_for('availability') }}\"><i class=\"bi bi-display me-2\"></i> Room Availability</a></li>\n            {% endif %}"
                )
                content = content.replace(
                    '<li class="nav-item mt-4"><hr class="text-light opacity-25"></li>\n            <li class="nav-item"><a class="nav-link text-white" href="{{ url_for(\'academic\') }}"><i class="bi bi-database me-2"></i> Master Data</a></li>',
                    "{% if current_user.role == 'Admin' %}\n            <li class=\"nav-item mt-4\"><hr class=\"text-light opacity-25\"></li>\n            <li class=\"nav-item\"><a class=\"nav-link text-white\" href=\"{{ url_for('academic') }}\"><i class=\"bi bi-database me-2\"></i> Master Data</a></li>\n            {% endif %}"
                )
                content = content.replace(
                    '<a class="nav-link text-white mb-3" href="{{ url_for(\'logout\') }}"><i class="bi bi-box-arrow-right me-2"></i> Logout</a>',
                    '<form method="POST" action="{{ url_for(\'logout\') }}" class="mb-3"><input type="hidden" name="csrf_token" value="{{ csrf_token() }}"><button type="submit" class="nav-link text-white w-100 text-start border-0 bg-transparent"><i class="bi bi-box-arrow-right me-2"></i> Logout</button></form>'
                )
            FILES[filename] = content


def create_project():
    harden_generated_files()
    print("Overwriting files with corrected Dashboard UI...")
    for filename, content in FILES.items():
        folder = os.path.dirname(filename)
        if folder and not os.path.exists(folder):
            os.makedirs(folder)
        
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"Updated: {filename}")
    
    print("\nUI Update Complete! 🎉")
    print("Next steps:")
    print("1. Run: python setup.py")
    print("2. Set SEED_ADMIN_PASSWORD, then run: python seed.py")
    print("3. Run: python app.py")

if __name__ == "__main__":
    create_project()
