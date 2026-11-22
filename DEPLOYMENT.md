# Timetable system setup and operations

## Requirements

Use Python 3.11 or newer. Keep secrets and local data out of source control. The project ignores `.env`, SQLite files, Python bytecode, virtual environments, and test output.

## Local setup (PowerShell)

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
$env:FLASK_SECRET_KEY = python -c "import secrets; print(secrets.token_hex(32))"
```

The app defaults to `timetable.db` in the project folder. Set `DATABASE_URL` to use another database. For example, a PostgreSQL URL can be used after installing its SQLAlchemy driver.

## Database migrations

Migrations are managed with Flask-Migrate/Alembic. The initial schema migration is committed in `migrations/versions`.

For a new database:

```powershell
python -m flask --app app db upgrade
```

For an existing database created with the old `db.create_all()` setup, back it up first and verify its tables match the initial migration. Mark that schema as the initial baseline once:

```powershell
Copy-Item timetable.db timetable.db.backup
python -m flask --app app db stamp head
```

After changing SQLAlchemy models, create and review a migration, then apply it:

```powershell
python -m flask --app app db migrate -m "describe schema change"
# Review the generated file in migrations/versions before applying it
python -m flask --app app db upgrade
```

Do not edit an already-applied migration; add a new revision instead. `db.create_all()` is not run automatically by the app.

## Optional demo data

`seed.py` intentionally deletes all current data. Only use it for a disposable local database. Set a temporary administrator password, then explicitly confirm the reset:

```powershell
$env:SEED_ADMIN_PASSWORD = 'use-a-temporary-strong-password'
python seed.py --reset
Remove-Item Env:SEED_ADMIN_PASSWORD
```

The seeded `admin` account is an administrator. Change its password before using the data beyond local development.

## Tests

```powershell
python -m pytest -q
```

Tests use a temporary SQLite database and disable CSRF only within the test app.

## Run locally

```powershell
python -m flask --app app db upgrade
python app.py
```

## Generate a schedule

1. In **Master Data → Instructor Subjects**, assign one or more eligible instructors to each subject for the selected term.
2. In **Master Data → Section Subjects**, assign the subjects each section needs for that term.
3. Open **Create Schedule**, select the term, then choose **Auto-Generate**. The generator creates one class per section-subject assignment, selects an eligible instructor with no timetable conflict, and checks course duration, room capacity, room type, and availability.
4. If a subject has no instructor assignment, or no valid room and time can be found, the system reports it so the assignment can be corrected or the pending schedule handled manually.

Assignments are term-specific. After pulling this version, apply the new assignment tables with `python -m flask --app app db upgrade` before using the new tabs.

For local debugging only, set `$env:FLASK_DEBUG = '1'`. Debug mode is off by default. New registrations are Instructor accounts. Promote an existing account with:

```powershell
python -m flask --app app make-admin Admin01@gmail.com
```

## Production (Windows)

Configure `APP_ENV=production`, a unique `FLASK_SECRET_KEY`, and a persistent `DATABASE_URL` in the service environment. Never commit these values. Apply migrations before starting the service:

```powershell
python -m flask --app app db upgrade
python -m waitress --listen=127.0.0.1:8000 app:app
```

Terminate HTTPS at a reverse proxy and keep the service bound to localhost when the proxy runs on the same machine.
