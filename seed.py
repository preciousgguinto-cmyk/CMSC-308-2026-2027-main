from datetime import time
import argparse
import os
from app import app, db, Term, Course, Faculty, Room, Section, Availability, Schedule, User
from werkzeug.security import generate_password_hash

def seed(admin_password):
    with app.app_context():
        print("Wiping old database...")
        db.drop_all()   # Wipes old data
        db.create_all()
        
        # Create Admin
        db.session.add(User(username="admin", password_hash=generate_password_hash(admin_password), role="Admin"))
        db.session.commit()

        term = Term(name="1st Semester 2026 - 2027")
        db.session.add(term)

        # 1. FACULTY
        f_reyes = Faculty(name="MR. REYES", department="CCS")
        f_rivano = Faculty(name="MS RIVANO", department="CCS")
        f_bernardino = Faculty(name="MR. BERNARDINO", department="CCS")
        f_sotomayor = Faculty(name="MR. SOTOMAYOR", department="CCS")
        f_garbo = Faculty(name="MISS GARBO", department="CCS")
        
        db.session.add_all([f_reyes, f_rivano, f_bernardino, f_sotomayor, f_garbo])

        # 2. ROOMS
        r_rm107 = Room(code="RM 107", capacity=45, room_type="lecture")
        r_rm105 = Room(code="RM 105", capacity=45, room_type="lecture")
        r_lab206 = Room(code="LAB 206", capacity=40, room_type="lab")
        r_rm106 = Room(code="RM 106", capacity=45, room_type="lecture")
        r_maclab = Room(code="MACLAB", capacity=40, room_type="lab")
        r_netlab = Room(code="NETLAB", capacity=40, room_type="lab")
        r_rm202 = Room(code="RM 202", capacity=45, room_type="lecture")

        db.session.add_all([r_rm107, r_rm105, r_lab206, r_rm106, r_maclab, r_netlab, r_rm202])

        # 3. COURSES
        c_csmc305 = Course(code="CSMC 305", title="Discrete Structures", units=3, room_type="lecture")
        c_csmc307 = Course(code="CSMC 307", title="Networking 1", units=3, room_type="lecture")
        c_csst101 = Course(code="CSST 101", title="Statistics", units=3, room_type="lab")
        c_csmc309 = Course(code="CSMC 309", title="Systems Integration", units=3, room_type="lab")
        c_csmc306 = Course(code="CSMC 306", title="Database Management", units=3, room_type="lab")
        c_csmc308 = Course(code="CSMC 308", title="Programming Languages", units=3, room_type="lab")
        c_csst102 = Course(code="CSST 102", title="Machine Learning", units=3, room_type="lab")
        c_csmc310 = Course(code="CSMC 310", title="Software Engineering", units=3, room_type="lab")

        db.session.add_all([c_csmc305, c_csmc307, c_csst101, c_csmc309, c_csmc306, c_csmc308, c_csst102, c_csmc310])

        # 4. SECTIONS
        s_bscs3a = Section(name="BSCS 3A", program="BS Computer Science", size=40)
        s_bscs3b = Section(name="BSCS 3B", program="BS Computer Science", size=40)
        db.session.add_all([s_bscs3a, s_bscs3b])
        db.session.commit()

        # 5. SCHEDULES
        scheds = [
            # ==========================================
            # BSCS 3A SCHEDULE
            # ==========================================
            # MONDAY
            Schedule(term_id=term.id, course_id=c_csmc305.id, faculty_id=f_reyes.id, section_id=s_bscs3a.id, room_id=r_rm107.id, day="Mon", start_time=time(11, 0), end_time=time(12, 0)),
            Schedule(term_id=term.id, course_id=c_csmc305.id, faculty_id=f_reyes.id, section_id=s_bscs3a.id, room_id=r_rm107.id, day="Mon", start_time=time(12, 0), end_time=time(13, 0)),

            # TUESDAY
            Schedule(term_id=term.id, course_id=c_csmc307.id, faculty_id=f_rivano.id, section_id=s_bscs3a.id, room_id=r_rm107.id, day="Tue", start_time=time(9, 0), end_time=time(10, 0)),
            Schedule(term_id=term.id, course_id=c_csst101.id, faculty_id=f_bernardino.id, section_id=s_bscs3a.id, room_id=r_rm105.id, day="Tue", start_time=time(11, 0), end_time=time(12, 0)),
            Schedule(term_id=term.id, course_id=c_csst101.id, faculty_id=f_bernardino.id, section_id=s_bscs3a.id, room_id=r_lab206.id, day="Tue", start_time=time(15, 0), end_time=time(16, 0)),
            Schedule(term_id=term.id, course_id=c_csst101.id, faculty_id=f_bernardino.id, section_id=s_bscs3a.id, room_id=r_lab206.id, day="Tue", start_time=time(16, 0), end_time=time(17, 0)),

            # WEDNESDAY
            Schedule(term_id=term.id, course_id=c_csmc309.id, faculty_id=f_sotomayor.id, section_id=s_bscs3a.id, room_id=r_lab206.id, day="Wed", start_time=time(8, 0), end_time=time(9, 0)),
            Schedule(term_id=term.id, course_id=c_csmc309.id, faculty_id=f_sotomayor.id, section_id=s_bscs3a.id, room_id=r_lab206.id, day="Wed", start_time=time(9, 0), end_time=time(10, 0)),
            Schedule(term_id=term.id, course_id=c_csmc306.id, faculty_id=f_reyes.id, section_id=s_bscs3a.id, room_id=r_lab206.id, day="Wed", start_time=time(11, 0), end_time=time(12, 0)),
            Schedule(term_id=term.id, course_id=c_csmc306.id, faculty_id=f_reyes.id, section_id=s_bscs3a.id, room_id=r_rm107.id, day="Wed", start_time=time(15, 0), end_time=time(16, 0)),

            # THURSDAY
            Schedule(term_id=term.id, course_id=c_csmc308.id, faculty_id=f_sotomayor.id, section_id=s_bscs3a.id, room_id=r_lab206.id, day="Thu", start_time=time(8, 0), end_time=time(9, 0)),
            Schedule(term_id=term.id, course_id=c_csmc308.id, faculty_id=f_sotomayor.id, section_id=s_bscs3a.id, room_id=r_lab206.id, day="Thu", start_time=time(9, 0), end_time=time(10, 0)),
            Schedule(term_id=term.id, course_id=c_csmc308.id, faculty_id=f_sotomayor.id, section_id=s_bscs3a.id, room_id=r_rm107.id, day="Thu", start_time=time(10, 0), end_time=time(11, 0)),
            Schedule(term_id=term.id, course_id=c_csmc309.id, faculty_id=f_sotomayor.id, section_id=s_bscs3a.id, room_id=r_rm107.id, day="Thu", start_time=time(14, 0), end_time=time(15, 0)),

            # FRIDAY
            Schedule(term_id=term.id, course_id=c_csst102.id, faculty_id=f_sotomayor.id, section_id=s_bscs3a.id, room_id=r_lab206.id, day="Fri", start_time=time(11, 0), end_time=time(12, 0)),
            Schedule(term_id=term.id, course_id=c_csst102.id, faculty_id=f_sotomayor.id, section_id=s_bscs3a.id, room_id=r_rm106.id, day="Fri", start_time=time(15, 0), end_time=time(16, 0)),

            # SATURDAY
            Schedule(term_id=term.id, course_id=c_csmc310.id, faculty_id=f_garbo.id, section_id=s_bscs3a.id, room_id=r_maclab.id, day="Sat", start_time=time(8, 0), end_time=time(9, 0)),
            Schedule(term_id=term.id, course_id=c_csmc310.id, faculty_id=f_garbo.id, section_id=s_bscs3a.id, room_id=r_maclab.id, day="Sat", start_time=time(9, 0), end_time=time(10, 0)),
            Schedule(term_id=term.id, course_id=c_csmc310.id, faculty_id=f_garbo.id, section_id=s_bscs3a.id, room_id=r_maclab.id, day="Sat", start_time=time(11, 0), end_time=time(12, 0)),


            # ==========================================
            # BSCS 3B SCHEDULE
            # ==========================================
            # MONDAY
            Schedule(term_id=term.id, course_id=c_csmc309.id, faculty_id=f_sotomayor.id, section_id=s_bscs3b.id, room_id=r_lab206.id, day="Mon", start_time=time(7, 0), end_time=time(8, 0)),
            Schedule(term_id=term.id, course_id=c_csmc309.id, faculty_id=f_sotomayor.id, section_id=s_bscs3b.id, room_id=r_lab206.id, day="Mon", start_time=time(8, 0), end_time=time(9, 0)),
            Schedule(term_id=term.id, course_id=c_csst101.id, faculty_id=f_bernardino.id, section_id=s_bscs3b.id, room_id=r_lab206.id, day="Mon", start_time=time(11, 0), end_time=time(12, 0)),
            Schedule(term_id=term.id, course_id=c_csst101.id, faculty_id=f_bernardino.id, section_id=s_bscs3b.id, room_id=r_lab206.id, day="Mon", start_time=time(12, 0), end_time=time(13, 0)),
            Schedule(term_id=term.id, course_id=c_csst101.id, faculty_id=f_bernardino.id, section_id=s_bscs3b.id, room_id=r_rm107.id, day="Mon", start_time=time(15, 0), end_time=time(16, 0)),

            # TUESDAY
            Schedule(term_id=term.id, course_id=c_csmc308.id, faculty_id=f_sotomayor.id, section_id=s_bscs3b.id, room_id=r_lab206.id, day="Tue", start_time=time(7, 0), end_time=time(8, 0)),
            Schedule(term_id=term.id, course_id=c_csmc308.id, faculty_id=f_sotomayor.id, section_id=s_bscs3b.id, room_id=r_lab206.id, day="Tue", start_time=time(8, 0), end_time=time(9, 0)),
            Schedule(term_id=term.id, course_id=c_csmc305.id, faculty_id=f_reyes.id, section_id=s_bscs3b.id, room_id=r_rm107.id, day="Tue", start_time=time(11, 0), end_time=time(12, 0)),

            # WEDNESDAY
            Schedule(term_id=term.id, course_id=c_csmc307.id, faculty_id=f_rivano.id, section_id=s_bscs3b.id, room_id=r_rm107.id, day="Wed", start_time=time(9, 0), end_time=time(10, 0)),
            Schedule(term_id=term.id, course_id=c_csst102.id, faculty_id=f_bernardino.id, section_id=s_bscs3b.id, room_id=r_rm106.id, day="Wed", start_time=time(11, 0), end_time=time(12, 0)),
            Schedule(term_id=term.id, course_id=c_csst102.id, faculty_id=f_bernardino.id, section_id=s_bscs3b.id, room_id=r_lab206.id, day="Wed", start_time=time(15, 0), end_time=time(16, 0)),
            Schedule(term_id=term.id, course_id=c_csst102.id, faculty_id=f_bernardino.id, section_id=s_bscs3b.id, room_id=r_lab206.id, day="Wed", start_time=time(16, 0), end_time=time(17, 0)),

            # THURSDAY
            Schedule(term_id=term.id, course_id=c_csmc306.id, faculty_id=f_reyes.id, section_id=s_bscs3b.id, room_id=r_lab206.id, day="Thu", start_time=time(11, 0), end_time=time(12, 0)),
            Schedule(term_id=term.id, course_id=c_csmc306.id, faculty_id=f_reyes.id, section_id=s_bscs3b.id, room_id=r_lab206.id, day="Thu", start_time=time(12, 0), end_time=time(13, 0)),
            Schedule(term_id=term.id, course_id=c_csmc306.id, faculty_id=f_reyes.id, section_id=s_bscs3b.id, room_id=r_rm202.id, day="Thu", start_time=time(15, 0), end_time=time(16, 0)),

            # FRIDAY
            Schedule(term_id=term.id, course_id=c_csmc309.id, faculty_id=f_sotomayor.id, section_id=s_bscs3b.id, room_id=r_rm107.id, day="Fri", start_time=time(7, 0), end_time=time(8, 0)),
            Schedule(term_id=term.id, course_id=c_csmc309.id, faculty_id=f_sotomayor.id, section_id=s_bscs3b.id, room_id=r_rm107.id, day="Fri", start_time=time(8, 0), end_time=time(9, 0)),
            Schedule(term_id=term.id, course_id=c_csmc308.id, faculty_id=f_sotomayor.id, section_id=s_bscs3b.id, room_id=r_rm107.id, day="Fri", start_time=time(9, 0), end_time=time(10, 0)),
            Schedule(term_id=term.id, course_id=c_csmc310.id, faculty_id=f_garbo.id, section_id=s_bscs3b.id, room_id=r_netlab.id, day="Fri", start_time=time(11, 0), end_time=time(12, 0)),
            Schedule(term_id=term.id, course_id=c_csmc310.id, faculty_id=f_garbo.id, section_id=s_bscs3b.id, room_id=r_netlab.id, day="Fri", start_time=time(12, 0), end_time=time(13, 0)),
            Schedule(term_id=term.id, course_id=c_csmc310.id, faculty_id=f_garbo.id, section_id=s_bscs3b.id, room_id=r_netlab.id, day="Fri", start_time=time(15, 0), end_time=time(16, 0)),
        ]
        
        db.session.add_all(scheds)
        db.session.commit()
        print("BSCS 3A and 3B Schedules loaded successfully!")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Load demo data. This replaces all current database contents.')
    parser.add_argument('--reset', action='store_true', help='confirm destructive database reset')
    args = parser.parse_args()
    if not args.reset:
        parser.error('refusing to wipe data without --reset')
    password = os.environ.get('SEED_ADMIN_PASSWORD')
    if not password:
        parser.error('set SEED_ADMIN_PASSWORD to a temporary strong password before seeding')
    seed(password)