# BONASO Data Portal - Django Backend

## Quickstart
### 1. Create and activate venv
```bash
cd c:\Projects\django_backend
python -m venv venv
venv\Scripts\activate
```

### 2. Install dependencies
```bash
pip install -r requirements.txt
```

### 3. Configure environment
Create `.env` in `c:\Projects\django_backend` and set required values:
```
DJANGO_SECRET_KEY=...
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1,192.168.0.112
CORS_ALLOWED_ORIGINS=http://localhost:3000,http://127.0.0.1:3000,http://192.168.0.112:3000
```

### 4. Run migrations
```bash
python manage.py migrate
```

### 5. Start server
```bash
python manage.py runserver 0.0.0.0:8000
```

## Architecture
The backend is a Django REST Framework API with app-level modularity:
- `organizations`: org hierarchy
- `projects`: projects, tasks, deadlines
- `indicators`: indicator definitions and assessments
- `aggregates`: aggregate entries and templates
- `analysis`: reports and dashboards
- `respondents`: respondent records and interactions
- `events`: activities and participants
- `social`: social content tracking
- `flags`: data quality flags
- `users`: auth and user management
- `profiles`, `uploads`, `messaging`: auxiliary services

## API
Base URL: `http://localhost:8000/api/`

### Auth
- `POST /api/users/request-token/`
- `POST /api/users/token/refresh/`
- `GET /api/users/me/`

### Organizations
- `GET /api/organizations/`
- `GET /api/organizations/:id/`

### Projects, Tasks, Deadlines
- `GET /api/manage/projects/`
- `GET /api/manage/projects/:id/`
- `GET /api/manage/tasks/`
- `GET /api/manage/deadlines/`

### Indicators
- `GET /api/indicators/`
- `GET /api/indicators/categories/`

### Aggregates
- GET /api/aggregates/
- POST /api/aggregates/bulk_create/
- GET /api/aggregates/summary/
- GET /api/aggregates/templates/
- GET /api/aggregates/export/?format=csv|excel

### Analysis and Reports
- GET /api/analysis/dashboard/overview/
- GET /api/analysis/trends/:indicator_id/
- GET /api/analysis/trends/?indicator_ids=1,2,...
- GET /api/analysis/reports/
- POST /api/analysis/reports/
- GET /api/analysis/reports/:id/download/
- GET /api/analysis/scheduled-reports/
- POST /api/analysis/scheduled-reports/

### Respondents and Interactions
- `GET /api/record/respondents/`
- `GET /api/record/interactions/`

### Events
- GET /api/activities/
- GET /api/activities/types/
- GET /api/activities/stats/
- GET /api/activities/upcoming/
- POST /api/activities/participants/:id/mark_attendance/

### Social, Flags, Messaging
- `GET /api/social/posts/`
- `GET /api/flags/`
- `POST /api/flags/run-checks/`
- `GET /api/messages/`

## UI
The backend does not render UI. It serves JSON APIs consumed by the Next.js frontend.

## Data Model
### Core entities
- **Organization**: can be coordinator or sub-grantee (parent/child).
- **Project**: has participating organizations, tasks, deadlines.
- **Indicator**: metric definition (categories: HIV Prevention, Non-Communicable Diseases, Events); can be assigned to multiple orgs.
- **Aggregate**: data entry per indicator, org, project, and period.
- **User**: role-based access; optionally linked to org.

### Key relationships
- Organization -> Organization: parent/child
- Project -> Organization: many-to-many
- Indicator -> Organization: many-to-many
- Aggregate -> Indicator: many-to-one
- Aggregate -> Organization: many-to-one
- Aggregate -> Project: many-to-one

## Deployment
1. Set `DEBUG=False` and configure PostgreSQL in `.env`.
2. Set `ALLOWED_HOSTS` and `CORS_ALLOWED_ORIGINS`.
3. Run:
```bash
python manage.py migrate
python manage.py collectstatic
```
4. Run with Gunicorn:
```bash
gunicorn core.wsgi:application
```

## Troubleshooting
- **401 Unauthorized**: token expired; re-login or refresh.
- **DisallowedHost**: add host IP to `ALLOWED_HOSTS`.
- **CORS errors**: update `CORS_ALLOWED_ORIGINS`.
- **Missing tables**: run `python manage.py migrate`.


