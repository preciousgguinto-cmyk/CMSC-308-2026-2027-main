import pytest
from datetime import time
from flask import template_rendered
from werkzeug.security import generate_password_hash

import app as system


@pytest.fixture()
def app(tmp_path):
    system.app.config.update(
        TESTING=True,
        WTF_CSRF_ENABLED=False,
        SQLALCHEMY_DATABASE_URI=f"sqlite:///{tmp_path / 'test.db'}",
        SECRET_KEY="test-secret",
    )
    with system.app.app_context():
        system.db.drop_all()
        system.db.create_all()
        admin = system.User(username="admin", password_hash=generate_password_hash("secret"), role="Admin")
        instructor = system.User(username="teacher", password_hash=generate_password_hash("secret"), role="Instructor")
        term1, term2 = system.Term(name="Term One"), system.Term(name="Term Two")
        course = system.Course(code="CS101", title="Intro", units=2, room_type="lecture")
        faculty = system.Faculty(name="Ada")
        room = system.Room(code="R1", capacity=40, room_type="lecture")
        section = system.Section(name="A", size=30)
        system.db.session.add_all([admin, instructor, term1, term2, course, faculty, room, section])
        system.db.session.commit()
        yield system.app
        system.db.session.remove()
        system.db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


def login(client, username="admin"):
    return client.post("/login", data={"username": username, "password": "secret"}, follow_redirects=True)


def records():
    return {"term": system.Term.query.order_by(system.Term.id).first(), "other": system.Term.query.order_by(system.Term.id.desc()).first(),
            "course": system.Course.query.first(), "faculty": system.Faculty.query.first(), "room": system.Room.query.first(), "section": system.Section.query.first()}


def test_login_and_admin_permissions(client):
    assert client.get("/academic").status_code == 302
    login(client, "teacher")
    assert client.get("/academic").status_code == 403
    assert client.post("/academic/course/add", data={"code": "CS202", "title": "Unauthorized", "units": 1}).status_code == 403


def test_conflicts_are_scoped_to_term(app):
    with app.app_context():
        r = records(); term, other = r["term"], r["other"]
        scheduled = system.Schedule(term_id=term.id, course_id=r["course"].id, faculty_id=r["faculty"].id, section_id=r["section"].id, room_id=r["room"].id, day="Mon", start_time=time(9), end_time=time(11))
        system.db.session.add(scheduled); system.db.session.commit()
        candidate = {"term_id": other.id, "day": "Mon", "start_time": time(10), "end_time": time(12), "faculty_id": r["faculty"].id, "room_id": r["room"].id, "section_id": r["section"].id}
        assert system.check_schedule_conflicts(candidate, [scheduled]) == []
        candidate["term_id"] = term.id
        assert len(system.check_schedule_conflicts(candidate, [scheduled])) == 3


def test_reports_only_include_selected_term_pending(app, client):
    captured = {}
    def receiver(sender, template, context, **extra):
        if template.name == "reports.html": captured.update(context)
    template_rendered.connect(receiver, app)
    with app.app_context():
        r = records()
        first = system.Schedule(term_id=r["term"].id, course_id=r["course"].id, faculty_id=r["faculty"].id, section_id=r["section"].id)
        second = system.Schedule(term_id=r["other"].id, course_id=r["course"].id, faculty_id=r["faculty"].id, section_id=r["section"].id)
        system.db.session.add_all([first, second]); system.db.session.commit(); selected_id = r["term"].id; first_id = first.id
    login(client)
    response = client.get(f"/reports?term_id={selected_id}")
    template_rendered.disconnect(receiver, app)
    assert response.status_code == 200
    assert [item.id for item in captured["pending"]] == [first_id]


def test_auto_generation_uses_course_duration_and_term(app):
    with app.app_context():
        r = records()
        target = system.Schedule(term_id=r["term"].id, course_id=r["course"].id, faculty_id=r["faculty"].id, section_id=r["section"].id)
        other = system.Schedule(term_id=r["other"].id, course_id=r["course"].id, faculty_id=r["faculty"].id, section_id=r["section"].id, room_id=r["room"].id, day="Mon", start_time=time(7), end_time=time(9))
        system.db.session.add_all([target, other]); system.db.session.commit()
        assigned, pending = system.auto_generate(r["term"].id)
        assert assigned == 1 and pending == []
        assert target.end_time.hour - target.start_time.hour == 2
        assert target.term_id == r["term"].id


def test_validation_rejects_unknown_room_type_and_bad_schedule_ids(client):
    login(client)
    response = client.post("/academic/room/add", data={"code": "BAD", "capacity": "25", "room_type": "pool"})
    assert response.status_code == 302
    assert system.Room.query.filter_by(code="BAD").first() is None
    response = client.post("/schedules/add", data={"term_id": "999", "course_id": "999", "faculty_id": "999", "section_id": "999"})
    assert response.status_code == 302
    r = records()
    response = client.post("/schedules/add", data={"term_id": r["term"].id, "course_id": r["course"].id, "faculty_id": r["faculty"].id, "section_id": r["section"].id, "day": "Mon"})
    assert response.status_code == 302
    with system.app.app_context():
        assert system.Schedule.query.count() == 0


def test_pdf_export_returns_pdf_for_selected_term(client, app):
    with app.app_context():
        r = records()
        system.db.session.add(system.Schedule(term_id=r["term"].id, course_id=r["course"].id, faculty_id=r["faculty"].id, section_id=r["section"].id, room_id=r["room"].id, day="Mon", start_time=time(9), end_time=time(11)))
        system.db.session.commit(); term_id, section_id = r["term"].id, r["section"].id
    login(client)
    response = client.get(f"/download_pdf?term_id={term_id}&section_id={section_id}")
    assert response.status_code == 200
    assert response.mimetype == "application/pdf"
    assert response.data.startswith(b"%PDF")
