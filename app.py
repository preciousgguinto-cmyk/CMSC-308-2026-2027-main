

import os
import secrets
from functools import wraps

import click
from flask import abort
from flask_wtf.csrf import CSRFProtect
from xhtml2pdf import pisa
from io import BytesIO
from flask import make_response
from datetime import time, datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from flask_migrate import Migrate
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
app = Flask(__name__)
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
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///' + os.path.join(BASE_DIR, 'timetable.db'))
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)
migrate = Migrate(app, db)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message_category = 'warning'


def admin_required(view):
    """Require an authenticated administrator for management actions."""
    @wraps(view)
    @login_required
    def wrapped_view(*args, **kwargs):
        if current_user.role != 'Admin':
            abort(403)
        return view(*args, **kwargs)
    return wrapped_view


@app.cli.command('make-admin')
@click.argument('username')
def make_admin(username):
    """Promote an existing registered account to administrator."""
    user = User.query.filter_by(username=username).first()
    if user is None:
        raise click.ClickException(f'No account found for {username!r}.')
    user.role = 'Admin'
    db.session.commit()
    click.echo(f'{username} is now an administrator.')

ROOM_TYPES = {'lecture', 'lab'}
DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']
TIME_SLOTS = [
    (time(7, 0), time(8, 0)), (time(8, 0), time(9, 0)), (time(9, 0), time(10, 0)),
    (time(10, 0), time(11, 0)), (time(11, 0), time(12, 0)), (time(12, 0), time(13, 0)),
    (time(13, 0), time(14, 0)), (time(14, 0), time(15, 0)), (time(15, 0), time(16, 0)),
    (time(16, 0), time(17, 0)),
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

class FacultyCourseAssignment(db.Model):
    """A course an instructor is allowed to teach in a specific term."""
    id = db.Column(db.Integer, primary_key=True)
    term_id = db.Column(db.Integer, db.ForeignKey('term.id'), nullable=False)
    faculty_id = db.Column(db.Integer, db.ForeignKey('faculty.id'), nullable=False)
    course_id = db.Column(db.Integer, db.ForeignKey('course.id'), nullable=False)
    __table_args__ = (db.UniqueConstraint('term_id', 'faculty_id', 'course_id', name='uq_term_faculty_course'),)
    term = db.relationship('Term')
    faculty = db.relationship('Faculty')
    course = db.relationship('Course')

class SectionCourseAssignment(db.Model):
    """A course required by a section in a specific term."""
    id = db.Column(db.Integer, primary_key=True)
    term_id = db.Column(db.Integer, db.ForeignKey('term.id'), nullable=False)
    section_id = db.Column(db.Integer, db.ForeignKey('section.id'), nullable=False)
    course_id = db.Column(db.Integer, db.ForeignKey('course.id'), nullable=False)
    __table_args__ = (db.UniqueConstraint('term_id', 'section_id', 'course_id', name='uq_term_section_course'),)
    term = db.relationship('Term')
    section = db.relationship('Section')
    course = db.relationship('Course')

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

@app.errorhandler(SQLAlchemyError)
def handle_database_error(error):
    db.session.rollback()
    app.logger.exception('Database operation failed')
    if request.path.startswith('/api/') or request.accept_mimetypes.best == 'application/json':
        return {'error': 'A database error occurred. Please try again.'}, 500
    flash('A database error occurred. No changes were saved.', 'danger')
    return redirect(request.referrer or url_for('index'))


class ConflictError(Exception): pass

class AutoGenerateResult:
    """Keep the original two-value unpacking while exposing missing mappings."""
    def __init__(self, assigned, unassigned, missing_instructors):
        self.assigned = assigned
        self.unassigned = unassigned
        self.missing_instructors = missing_instructors

    def __iter__(self):
        return iter((self.assigned, self.unassigned))

def overlaps(s1, e1, s2, e2):
    return s1 < e2 and e1 > s2

def check_schedule_conflicts(new, existing_schedules, exclude_id=None):
    conflicts = []
    if new.get('day') is None or new.get('start_time') is None or new.get('end_time') is None:
        return conflicts

    for s in existing_schedules:
        if s.id == exclude_id or s.term_id != new.get('term_id'): continue
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
    # Build missing course/section schedule rows from the two term-specific
    # assignment lists. Existing rows are kept, so rerunning generation is safe.
    existing = Schedule.query.filter_by(term_id=term_id).all()
    course_assignments = FacultyCourseAssignment.query.filter_by(term_id=term_id).all()
    faculty_by_course = {}
    for assignment in course_assignments:
        faculty_by_course.setdefault(assignment.course_id, []).append(assignment.faculty_id)

    section_assignments = SectionCourseAssignment.query.filter_by(term_id=term_id).all()
    section_assignments.sort(key=lambda a: (0 if a.course.room_type == 'lab' else 1, -a.section.size, a.course.code, a.section.name))
    missing_instructors = []
    for assignment in section_assignments:
        pair_exists = any(s.course_id == assignment.course_id and s.section_id == assignment.section_id for s in existing)
        if pair_exists:
            continue
        eligible_faculty = faculty_by_course.get(assignment.course_id, [])
        if not eligible_faculty:
            missing_instructors.append(f'{assignment.course.code}/{assignment.section.name}')
            continue
        # The least-loaded eligible instructor is the initial choice. If that
        # instructor has a conflict, the placement loop below tries the others.
        faculty_id = min(eligible_faculty, key=lambda fid: sum(s.faculty_id == fid for s in existing))
        sched = Schedule(term_id=term_id, course_id=assignment.course_id,
                         faculty_id=faculty_id, section_id=assignment.section_id)
        db.session.add(sched)
        existing.append(sched)
    db.session.flush()

    pending = [s for s in existing if s.is_pending]
    pending.sort(key=lambda s: (0 if s.course.room_type == 'lab' else 1, -s.section.size))
    assigned_count, still_unassigned = 0, []
    rooms = Room.query.order_by(Room.code).all()

    for sched in pending:
        eligible_faculty = faculty_by_course.get(sched.course_id, [sched.faculty_id])
        eligible_faculty = sorted(set(eligible_faculty), key=lambda fid: sum(s.faculty_id == fid for s in existing))
        placed = False
        for day in DAYS:
            for start, _ in TIME_SLOTS:
                end_dt = datetime.combine(datetime.today(), start) + timedelta(hours=sched.course.units or 1)
                if end_dt.time() > TIME_SLOTS[-1][1]:
                    continue
                end = end_dt.time()
                for faculty_id in eligible_faculty:
                    for room in rooms:
                        if check_room_suitability(room, sched.section, sched.course):
                            continue
                        candidate = {'term_id': term_id, 'day': day, 'start_time': start,
                                     'end_time': end, 'room_id': room.id, 'faculty_id': faculty_id,
                                     'section_id': sched.section_id, 'course_id': sched.course_id}
                        if not check_schedule_conflicts(candidate, existing, exclude_id=sched.id):
                            sched.faculty_id = faculty_id
                            sched.day, sched.start_time, sched.end_time, sched.room_id = day, start, end, room.id
                            assigned_count += 1
                            placed = True
                            break
                    if placed:
                        break
                if placed:
                    break
            if placed:
                break
        if not placed:
            still_unassigned.append(sched)

    db.session.commit()
    return AutoGenerateResult(assigned_count, still_unassigned, missing_instructors)

def parse_time(value):
    if not value: return None
    try: return datetime.strptime(value, '%H:%M').time()
    except ValueError: return None

def build_timetable(schedules):
    grid = {}
    for s in schedules:
        if s.day and s.start_time and s.end_time:
            for slot_start, slot_end in TIME_SLOTS:
                if overlaps(s.start_time, s.end_time, slot_start, slot_end):
                    grid.setdefault((s.day, slot_start.strftime('%H:%M')), []).append(s)
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
        flash('Invalid username or password.', 'login-error')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated: return redirect(url_for('index'))
    if request.method == 'POST':
        username = (request.form.get('username') or '').strip()
        password = request.form.get('password') or ''
        if not username or not password:
            flash('Enter both a username and password.', 'register-error')
        elif len(username) > 80:
            flash('Username must be 80 characters or fewer.', 'register-error')
        elif User.query.filter_by(username=username).first():
            flash('That email or username is already registered. Please log in or use another one.', 'register-error')
        else:
            try:
                db.session.add(User(username=username, password_hash=generate_password_hash(password)))
                db.session.commit()
                flash('Account created. Please log in.', 'register-success')
                return redirect(url_for('login'))
            except IntegrityError:
                db.session.rollback()
                flash('That email or username is already registered. Please log in or use another one.', 'register-error')
    return render_template('register.html')

@app.route('/logout', methods=['POST'])
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))


# MAIN ROUTES
@app.route('/')
@login_required
def index():
    sections = Section.query.all()
    
    # Get the selected section from the URL (default to the first one)
    section_id = request.args.get('section_id', type=int)
    if not section_id and sections:
        section_id = sections[0].id

    # Only fetch schedules for the selected section
    if section_id:
        all_scheds = Schedule.query.filter(
            Schedule.room_id.isnot(None),
            Schedule.section_id == section_id
        ).all()
    else:
        all_scheds = []

    grid = build_timetable(all_scheds)
    selected_section = db.session.get(Section, section_id) if section_id else None

    stats = {
        'courses': Course.query.count(), 
        'faculty': Faculty.query.count(), 
        'rooms': Room.query.count(), 
        'sections': Section.query.count(), 
        'schedules': len(all_scheds), 
        'pending': Schedule.query.filter(Schedule.room_id.is_(None), Schedule.section_id == section_id).count() if section_id else 0
    }
    
    return render_template('index.html', stats=stats, grid=grid, days=DAYS, time_slots=TIME_SLOTS, sections=sections, selected_section=selected_section)

@app.route('/academic')
@admin_required
def academic():
    return render_template(
        'academic.html', courses=Course.query.order_by(Course.code).all(),
        faculty=Faculty.query.order_by(Faculty.name).all(),
        rooms=Room.query.order_by(Room.code).all(),
        sections=Section.query.order_by(Section.name).all(), terms=Term.query.order_by(Term.id).all(),
        faculty_course_assignments=FacultyCourseAssignment.query.order_by(FacultyCourseAssignment.term_id, FacultyCourseAssignment.faculty_id).all(),
        section_course_assignments=SectionCourseAssignment.query.order_by(SectionCourseAssignment.term_id, SectionCourseAssignment.section_id).all())

@app.route('/academic/course/add', methods=['POST'])
@admin_required
def add_course():
    code, title = request.form.get('code', '').strip().upper(), request.form.get('title', '').strip()
    try: units = int(request.form.get('units', 3))
    except ValueError: flash('Units must be a number.', 'danger'); return redirect(url_for('academic'))
    room_type = request.form.get('room_type', 'lecture').strip().lower()
    if not code or not title or units <= 0 or room_type not in ROOM_TYPES: flash('Code, title, and positive units required.', 'danger'); return redirect(url_for('academic'))
    try:
        db.session.add(Course(code=code, title=title, units=units, room_type=room_type))
        db.session.commit(); flash(f"Course '{code}' added.", 'success')
    except IntegrityError: db.session.rollback(); flash(f"Course code '{code}' already exists.", 'danger')
    return redirect(url_for('academic'))

@app.route('/academic/course/<int:id>/delete', methods=['POST'])
@admin_required
def delete_course(id):
    c = db.session.get(Course, id)
    if not c: flash('Course not found.', 'danger')
    elif c.schedules or FacultyCourseAssignment.query.filter_by(course_id=c.id).first() or SectionCourseAssignment.query.filter_by(course_id=c.id).first(): flash(f"Cannot delete {c.code}: schedule or subject assignment(s) reference it.", 'danger')
    else: db.session.delete(c); db.session.commit(); flash(f"Course '{c.code}' deleted.", 'success')
    return redirect(url_for('academic'))

@app.route('/academic/faculty/add', methods=['POST'])
@admin_required
def add_faculty():
    name, dept = request.form.get('name', '').strip(), request.form.get('department', '').strip()
    if not name: flash('Faculty name is required.', 'danger'); return redirect(url_for('academic'))
    db.session.add(Faculty(name=name, department=dept))
    db.session.commit(); flash(f"Faculty '{name}' added.", 'success')
    return redirect(url_for('academic'))

@app.route('/academic/faculty/<int:id>/delete', methods=['POST'])
@admin_required
def delete_faculty(id):
    f = db.session.get(Faculty, id)
    if not f: flash('Faculty not found.', 'danger')
    elif f.schedules or FacultyCourseAssignment.query.filter_by(faculty_id=f.id).first(): flash(f"Cannot delete {f.name}: schedule or subject assignment(s) reference them.", 'danger')
    else: db.session.delete(f); db.session.commit(); flash(f"Faculty '{f.name}' deleted.", 'success')
    return redirect(url_for('academic'))

@app.route('/academic/room/add', methods=['POST'])
@admin_required
def add_room():
    code = request.form.get('code', '').strip().upper()
    try: cap = int(request.form.get('capacity', 30))
    except ValueError: flash('Capacity must be a number.', 'danger'); return redirect(url_for('academic'))
    room_type = request.form.get('room_type', 'lecture').strip().lower()
    if not code or cap <= 0 or room_type not in ROOM_TYPES: flash('Code and positive capacity required.', 'danger'); return redirect(url_for('academic'))
    try:
        db.session.add(Room(code=code, capacity=cap, room_type=room_type))
        db.session.commit(); flash(f"Room '{code}' added.", 'success')
    except IntegrityError: db.session.rollback(); flash(f"Room code '{code}' already exists.", 'danger')
    return redirect(url_for('academic'))

@app.route('/academic/room/<int:id>/delete', methods=['POST'])
@admin_required
def delete_room(id):
    r = db.session.get(Room, id)
    if not r: flash('Room not found.', 'danger')
    elif r.schedules: flash(f"Cannot delete {r.code}: schedule(s) reference it.", 'danger')
    else: db.session.delete(r); db.session.commit(); flash(f"Room '{r.code}' deleted.", 'success')
    return redirect(url_for('academic'))

@app.route('/academic/section/add', methods=['POST'])
@admin_required
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
@admin_required
def delete_section(id):
    s = db.session.get(Section, id)
    if not s: flash('Section not found.', 'danger')
    elif s.schedules or SectionCourseAssignment.query.filter_by(section_id=s.id).first(): flash(f"Cannot delete {s.name}: schedule or subject assignment(s) reference it.", 'danger')
    else: db.session.delete(s); db.session.commit(); flash(f"Section '{s.name}' deleted.", 'success')
    return redirect(url_for('academic'))

@app.route('/academic/term/add', methods=['POST'])
@admin_required
def add_term():
    name = request.form.get('name', '').strip()
    if not name: flash('Term name required.', 'danger'); return redirect(url_for('academic'))
    try:
        db.session.add(Term(name=name)); db.session.commit(); flash(f"Term '{name}' added.", 'success')
    except IntegrityError: db.session.rollback(); flash(f"Term '{name}' already exists.", 'danger')
    return redirect(url_for('academic'))

@app.route('/academic/term/<int:id>/delete', methods=['POST'])
@admin_required
def delete_term(id):
    t = db.session.get(Term, id)
    if not t: flash('Term not found.', 'danger')
    elif t.schedules or FacultyCourseAssignment.query.filter_by(term_id=t.id).first() or SectionCourseAssignment.query.filter_by(term_id=t.id).first(): flash(f"Cannot delete {t.name}: schedules or subject assignments reference it.", 'danger')
    else: db.session.delete(t); db.session.commit(); flash(f"Term '{t.name}' deleted.", 'success')
    return redirect(url_for('academic'))

@app.route('/academic/faculty-course-assignment/add', methods=['POST'])
@admin_required
def add_faculty_course_assignment():
    try:
        term_id = int(request.form.get('term_id', ''))
        faculty_id = int(request.form.get('faculty_id', ''))
        course_id = int(request.form.get('course_id', ''))
    except (TypeError, ValueError):
        flash('Select a term, instructor, and subject.', 'danger')
        return redirect(url_for('academic'))
    if not all([db.session.get(Term, term_id), db.session.get(Faculty, faculty_id), db.session.get(Course, course_id)]):
        flash('Select valid term, instructor, and subject records.', 'danger')
        return redirect(url_for('academic'))
    db.session.add(FacultyCourseAssignment(term_id=term_id, faculty_id=faculty_id, course_id=course_id))
    try:
        db.session.commit()
        flash('Subject assigned to instructor for this term.', 'success')
    except IntegrityError:
        db.session.rollback()
        flash('That instructor already has this subject assignment for the selected term.', 'warning')
    return redirect(url_for('academic'))

@app.route('/academic/faculty-course-assignment/<int:id>/delete', methods=['POST'])
@admin_required
def delete_faculty_course_assignment(id):
    assignment = db.session.get(FacultyCourseAssignment, id)
    if assignment:
        db.session.delete(assignment)
        db.session.commit()
        flash('Instructor subject assignment removed.', 'success')
    else:
        flash('Instructor subject assignment not found.', 'danger')
    return redirect(url_for('academic'))

@app.route('/academic/section-course-assignment/add', methods=['POST'])
@admin_required
def add_section_course_assignment():
    try:
        term_id = int(request.form.get('term_id', ''))
        section_id = int(request.form.get('section_id', ''))
        course_id = int(request.form.get('course_id', ''))
    except (TypeError, ValueError):
        flash('Select a term, section, and subject.', 'danger')
        return redirect(url_for('academic'))
    if not all([db.session.get(Term, term_id), db.session.get(Section, section_id), db.session.get(Course, course_id)]):
        flash('Select valid term, section, and subject records.', 'danger')
        return redirect(url_for('academic'))
    db.session.add(SectionCourseAssignment(term_id=term_id, section_id=section_id, course_id=course_id))
    try:
        db.session.commit()
        flash('Subject assigned to section for this term.', 'success')
    except IntegrityError:
        db.session.rollback()
        flash('That section already has this subject assignment for the selected term.', 'warning')
    return redirect(url_for('academic'))

@app.route('/academic/section-course-assignment/<int:id>/delete', methods=['POST'])
@admin_required
def delete_section_course_assignment(id):
    assignment = db.session.get(SectionCourseAssignment, id)
    if assignment:
        db.session.delete(assignment)
        db.session.commit()
        flash('Section subject assignment removed.', 'success')
    else:
        flash('Section subject assignment not found.', 'danger')
    return redirect(url_for('academic'))

@app.route('/availability')
@admin_required
def availability():
    return render_template('availability.html', availabilities=Availability.query.order_by(Availability.day).all(), faculty=Faculty.query.order_by(Faculty.name).all(), rooms=Room.query.order_by(Room.code).all(), days=DAYS)

@app.route('/availability/add', methods=['POST'])
@admin_required
def add_availability():
    entity, day = request.form.get('entity', ''), request.form.get('day', '')
    start, end = parse_time(request.form.get('start_time', '')), parse_time(request.form.get('end_time', ''))
    if not entity or day not in DAYS or not start or not end or start >= end:
        flash('Invalid entity, day, or time range.', 'danger'); return redirect(url_for('availability'))
    kind, _, eid = entity.partition(':')
    try: eid = int(eid)
    except ValueError: flash('Invalid entity.', 'danger'); return redirect(url_for('availability'))
    if kind == 'faculty' and db.session.get(Faculty, eid): db.session.add(Availability(faculty_id=eid, day=day, start_time=start, end_time=end))
    elif kind == 'room' and db.session.get(Room, eid): db.session.add(Availability(room_id=eid, day=day, start_time=start, end_time=end))
    else: flash('Select a valid faculty member or room.', 'danger'); return redirect(url_for('availability'))
    db.session.commit(); flash('Unavailability block added.', 'success')
    return redirect(url_for('availability'))

@app.route('/availability/<int:id>/delete', methods=['POST'])
@admin_required
def delete_availability(id):
    a = db.session.get(Availability, id)
    if a: db.session.delete(a); db.session.commit(); flash('Block removed.', 'success')
    return redirect(url_for('availability'))

@app.route('/schedules')
@admin_required
def schedules():
    all_scheds = Schedule.query.order_by(Schedule.day, Schedule.start_time).all()
    statuses = {}
    for s in all_scheds:
        if s.is_pending: statuses[s.id] = ('pending', []); continue
        new = {'term_id': s.term_id, 'day': s.day, 'start_time': s.start_time, 'end_time': s.end_time, 'room_id': s.room_id, 'faculty_id': s.faculty_id, 'section_id': s.section_id, 'course_id': s.course_id}
        msgs = check_schedule_conflicts(new, all_scheds, exclude_id=s.id) + check_room_suitability(s.room, s.section, s.course)
        statuses[s.id] = ('ok' if not msgs else 'conflict', msgs)
    return render_template('schedules.html', schedules=all_scheds, statuses=statuses, terms=Term.query.all(), courses=Course.query.order_by(Course.code).all(), faculty=Faculty.query.order_by(Faculty.name).all(), sections=Section.query.order_by(Section.name).all(), rooms=Room.query.order_by(Room.code).all(), days=DAYS)

@app.route('/schedules/add', methods=['POST'])
@admin_required
def add_schedule():
    try: term_id, course_id, faculty_id, section_id = int(request.form['term_id']), int(request.form['course_id']), int(request.form['faculty_id']), int(request.form['section_id'])
    except (KeyError, ValueError): flash('Select term, course, faculty, and section.', 'danger'); return redirect(url_for('schedules'))
    room_raw, day = request.form.get('room_id', '').strip(), request.form.get('day', '').strip() or None
    start, end = parse_time(request.form.get('start_time', '')), parse_time(request.form.get('end_time', ''))
    if room_raw and day and start and end:
        if day not in DAYS or not room_raw.isdigit(): flash('Invalid room or day.', 'danger'); return redirect(url_for('schedules'))
        if not all([db.session.get(Term, term_id), db.session.get(Course, course_id), db.session.get(Faculty, faculty_id), db.session.get(Section, section_id), db.session.get(Room, int(room_raw))]): flash('Select valid schedule records.', 'danger'); return redirect(url_for('schedules'))
        if start >= end: flash('Start must be before end.', 'danger'); return redirect(url_for('schedules'))
        course = db.session.get(Course, course_id)
        expected = (datetime.combine(datetime.today(), start) + timedelta(hours=course.units or 1)).time()
        if end != expected: flash(f"This course requires {course.units} hour(s); end time must be {expected.strftime('%H:%M')}.", 'danger'); return redirect(url_for('schedules'))
        new = {'term_id': term_id, 'day': day, 'start_time': start, 'end_time': end, 'room_id': int(room_raw), 'faculty_id': faculty_id, 'section_id': section_id, 'course_id': course_id}
        conflicts = check_schedule_conflicts(new, Schedule.query.filter_by(term_id=term_id).all()) + check_room_suitability(db.session.get(Room, int(room_raw)), db.session.get(Section, section_id), db.session.get(Course, course_id))
        if conflicts: flash(' | '.join(conflicts), 'danger'); return redirect(url_for('schedules'))
        db.session.add(Schedule(term_id=term_id, course_id=course_id, faculty_id=faculty_id, section_id=section_id, room_id=int(room_raw), day=day, start_time=start, end_time=end))
        db.session.commit(); flash('Schedule added.', 'success'); return redirect(url_for('schedules'))
    if not all([db.session.get(Term, term_id), db.session.get(Course, course_id), db.session.get(Faculty, faculty_id), db.session.get(Section, section_id)]): flash('Select valid term, course, faculty, and section.', 'danger'); return redirect(url_for('schedules'))
    if any([room_raw, day, start, end]): flash('Provide a room, day, start, and end together, or leave all four blank for a pending schedule.', 'danger'); return redirect(url_for('schedules'))
    db.session.add(Schedule(term_id=term_id, course_id=course_id, faculty_id=faculty_id, section_id=section_id))
    db.session.commit(); flash('Pending schedule added.', 'info'); return redirect(url_for('schedules'))

@app.route('/schedules/<int:id>/assign', methods=['POST'])
@admin_required
def assign_schedule(id):
    s = db.session.get(Schedule, id)
    if not s: flash('Schedule not found.', 'danger'); return redirect(url_for('schedules'))
    try: room_id, day = int(request.form['room_id']), request.form['day'].strip()
    except (KeyError, TypeError, ValueError): flash('Select a valid room and day.', 'danger'); return redirect(url_for('schedules'))
    if not db.session.get(Room, room_id) or day not in DAYS: flash('Select a valid room and day.', 'danger'); return redirect(url_for('schedules'))
    start, end = parse_time(request.form['start_time']), parse_time(request.form['end_time'])
    if not day or not start or not end or start >= end: flash('Invalid day or time.', 'danger'); return redirect(url_for('schedules'))
    expected_end = (datetime.combine(datetime.today(), start) + timedelta(hours=s.course.units or 1)).time()
    if end != expected_end: flash(f"This course requires {s.course.units} hour(s); end time must be {expected_end.strftime('%H:%M')}.", 'danger'); return redirect(url_for('schedules'))
    new = {'term_id': s.term_id, 'day': day, 'start_time': start, 'end_time': end, 'room_id': room_id, 'faculty_id': s.faculty_id, 'section_id': s.section_id, 'course_id': s.course_id}
    conflicts = check_schedule_conflicts(new, Schedule.query.filter_by(term_id=s.term_id).all(), exclude_id=s.id) + check_room_suitability(db.session.get(Room, room_id), s.section, s.course)
    if conflicts: flash(' | '.join(conflicts), 'danger'); return redirect(url_for('schedules'))
    s.room_id, s.day, s.start_time, s.end_time = room_id, day, start, end
    db.session.commit(); flash('Schedule assigned.', 'success'); return redirect(url_for('schedules'))

@app.route('/schedules/<int:id>/delete', methods=['POST'])
@admin_required
def delete_schedule(id):
    s = db.session.get(Schedule, id)
    if s: db.session.delete(s); db.session.commit(); flash('Schedule deleted.', 'success')
    return redirect(url_for('schedules'))

@app.route('/schedules/clear', methods=['POST'])
@admin_required
def clear_schedules():
    Schedule.query.delete(); db.session.commit(); flash('All schedules cleared.', 'success'); return redirect(url_for('schedules'))

@app.route('/conflicts')
@login_required
def conflicts():
    all_scheds = Schedule.query.all(); rows = []
    for s in [x for x in all_scheds if not x.is_pending]:
        new = {'term_id': s.term_id, 'day': s.day, 'start_time': s.start_time, 'end_time': s.end_time, 'room_id': s.room_id, 'faculty_id': s.faculty_id, 'section_id': s.section_id, 'course_id': s.course_id}
        rows.append({'schedule': s, 'messages': check_schedule_conflicts(new, all_scheds, exclude_id=s.id) + check_room_suitability(s.room, s.section, s.course)})
    return render_template('conflicts.html', rows=rows, total=len(rows))

@app.route('/generate', methods=['POST'])
@admin_required
def generate():
    term = db.session.get(Term, request.form.get('term_id', type=int))
    if not term: flash('Select a valid term.', 'danger'); return redirect(url_for('schedules'))
    result = auto_generate(term.id)
    assigned, unassigned = result
    missing_instructors = result.missing_instructors
    if assigned: flash(f'Auto-generator scheduled {assigned} class(es) for {term.name}.', 'success')
    if unassigned: flash(f"Could not find an available room and time for: {', '.join(f'{s.course.code}/{s.section.name}' for s in unassigned)}", 'warning')
    if missing_instructors: flash(f"Assign an instructor to these subjects for {term.name}: {', '.join(missing_instructors)}", 'warning')
    if not assigned and not unassigned and not missing_instructors:
        flash('No new section-subject assignments need scheduling for this term.', 'info')
    return redirect(url_for('schedules'))

@app.route('/reports')
@login_required
def reports():
    # 1. Default to 'section' view
    view = request.args.get('view', 'section')
    entity_id = request.args.get('entity_id', type=int)
    
    # 2. If no entity is selected, auto-pick the first section
    if not entity_id and view == 'section':
        first_sec = Section.query.first()
        if first_sec: 
            entity_id = first_sec.id
            
    requested_term_id = request.args.get('term_id', type=int)
    term_id = requested_term_id if requested_term_id and db.session.get(Term, requested_term_id) else (Term.query.first().id if Term.query.first() else None)
    
    # 3. Fetch the schedules
    selected_scheds, title = [], 'Select a view'
    if view and entity_id and term_id:
        if view == 'section': 
            selected_scheds = Schedule.query.filter_by(term_id=term_id, section_id=entity_id).all()
            sec = db.session.get(Section, entity_id)
            if sec: title = f"Timetable — Section {sec.name}"
        elif view == 'faculty': 
            selected_scheds = Schedule.query.filter_by(term_id=term_id, faculty_id=entity_id).all()
            fac = db.session.get(Faculty, entity_id)
            if fac: title = f"Timetable — {fac.name}"
        elif view == 'room': 
            selected_scheds = Schedule.query.filter_by(term_id=term_id, room_id=entity_id).all()
            room = db.session.get(Room, entity_id)
            if room: title = f"Timetable — Room {room.code}"
            
    grid = build_timetable(selected_scheds)
    
    # 4. Generate reports data
    room_util, faculty_load, pending = [], [], []
    if term_id:
        total_hours = len(DAYS) * (TIME_SLOTS[-1][1].hour - TIME_SLOTS[0][0].hour)
        for r in Room.query.all(): 
            room_schedules = Schedule.query.filter_by(term_id=term_id, room_id=r.id).all()
            used_hours = sum((datetime.combine(datetime.today(), x.end_time) - datetime.combine(datetime.today(), x.start_time)).total_seconds() / 3600 for x in room_schedules if x.start_time and x.end_time)
            room_util.append({'room': r, 'used': len(room_schedules), 'hours': used_hours, 'total_hours': total_hours, 'pct': min(100, round((used_hours / total_hours) * 100, 1))})
        for f in Faculty.query.all(): 
            faculty_load.append({'faculty': f, 'load': Schedule.query.filter_by(term_id=term_id, faculty_id=f.id).count()})
        pending = Schedule.query.filter_by(term_id=term_id, room_id=None).all()
        
    return render_template('reports.html', view=view, entity_id=entity_id, title=title, sections=Section.query.all(), faculty=Faculty.query.all(), rooms=Room.query.all(), terms=Term.query.all(), term_id=term_id, grid=grid, days=DAYS, time_slots=TIME_SLOTS, room_util=room_util, faculty_load=faculty_load, pending=pending)

@app.route('/download_pdf')
@login_required
def download_pdf():
    section_id = request.args.get('section_id', type=int)
    term_id = request.args.get('term_id', type=int)
    if section_id and not db.session.get(Section, section_id): abort(404)
    if term_id and not db.session.get(Term, term_id): abort(404)
    term_id = term_id or (Term.query.first().id if Term.query.first() else None)
    
    if section_id:
        all_scheds = Schedule.query.filter(Schedule.room_id.isnot(None), Schedule.section_id == section_id, Schedule.term_id == term_id).all()
        sec = db.session.get(Section, section_id)
    else:
        all_scheds = Schedule.query.filter(Schedule.room_id.isnot(None), Schedule.term_id == term_id).all()
        sec = None
        
    grid = build_timetable(all_scheds)
    term = db.session.get(Term, term_id) if term_id else None
    
    html = render_template('pdf_template.html', grid=grid, days=DAYS, time_slots=TIME_SLOTS, term=term, section=sec)
    
    result = BytesIO()
    pdf = pisa.pisaDocument(BytesIO(html.encode("utf-8")), result)
    
    if not pdf.err:
        response = make_response(result.getvalue())
        response.headers['Content-Type'] = 'application/pdf'
        response.headers['Content-Disposition'] = 'attachment; filename=Master_Timetable.pdf'
        return response
        
    return "Error generating PDF", 400


if __name__ == '__main__':
    app.run(debug=app.config['DEBUG'])
