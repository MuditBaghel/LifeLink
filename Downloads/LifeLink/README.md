# LifeLink — Blood Donation & Emergency Donor Coordination

A Django web application that connects voluntary blood donors with patients who need blood,
supports emergency requests, donation camps with QR check-in, verified donation records,
certificates and achievements, and gives administrators a working operations console.

## Stack

| Layer | Choice |
| --- | --- |
| Backend | Django 5.2, Python 3.11 |
| Database | SQLite |
| Templates | Django templates (server rendered) |
| UI | Bootstrap 5.3 with a custom design system (`static/css/tokens.css`, `static/css/app.css`) |
| Icons | Bootstrap Icons (bundled locally) |
| Fonts | Archivo, Source Sans 3, JetBrains Mono (bundled locally) |
| QR codes | `qrcode` (generated on the server, PNG data URI) |
| PDF certificates | ReportLab |
| Images | Pillow for profile uploads |

Everything runs locally. No paid API or external service is required at runtime; fonts, icons
and Bootstrap are vendored in `static/vendor/` so the demo works without internet.

## Getting started

```powershell
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py seed_demo
python manage.py runserver
```

Open <http://127.0.0.1:8000/>.

### Demonstration accounts

Created by `python manage.py seed_demo` (local demonstration only):

| Role | Username | Password |
| --- | --- | --- |
| Administrator | `admin` | `LifeLink@2026` |
| Donor | `priya.donor` | `LifeLink@2026` |
| Recipient | `rahul.recipient` | `LifeLink@2026` |

All demo donors and recipients use the same password. The credentials are also listed at
`/demo-accounts/`. The seeder refuses to run when `DEBUG` is off unless `--force` is passed,
and it never deletes or overwrites existing accounts or records.

The dataset is idempotent: running `seed_demo` twice leaves the same rows. It creates
1 administrator, 17 donors, 6 recipients, 12 requests, 4 camps, 17 camp registrations,
22 donation records (19 verified, 3 awaiting verification), volunteer duties and feedback.

## Applications

| App | Responsibility |
| --- | --- |
| `core` | Public pages (home, about, contact, FAQ, demo accounts), shared form mixins, editorial copy |
| `accounts` | Custom user with role, donor/recipient/volunteer profiles, auth, donor discovery |
| `blood` | Blood requests, lifecycle events, donor responses, compatibility matching, SOS |
| `camps` | Camps, registrations with QR tokens, volunteer duties, feedback, check-in |
| `donations` | Donation records, verification, certificates (PDF), achievement catalogue |
| `notifications` | In-app notifications with dedupe keys and per-user preferences |
| `console` | Donor/recipient dashboards, administrator console, analytics, CSV exports, seeder |

## Workflows that actually write data

- **Matching** — a request is matched against donor blood groups using a red-cell compatibility
  table, then filtered by availability, the 90-day gap and age. Every candidate carries the
  reasons it matched (group, city, availability, verification, donation history).
- **Request lifecycle** — `created → searching → potential donors → responses → coordination →
  fulfilled`, with `cancelled` allowed from any open state. Transitions are validated and written
  to `RequestStatusEvent`, which is the timeline shown on the request page.
- **Responses** — donors respond once per request; recipients confirm, decline or mark a donation
  completed. Completing a response creates an unverified donation record and recalculates units.
- **Camps** — capacity is checked inside a transaction, duplicate registrations are rejected by a
  unique constraint, and each registration gets a UUID QR token. Staff-only check-in records the
  donation as pending verification.
- **Verification** — only an administrator can verify a donation. Verification issues the
  certificate, sets the donor's last donation date and grants achievements.
- **Certificates** — PDF generated on download, owner/admin only, with a public verification page
  that shows no contact details.
- **Exports** — CSV for donations, requests, users, camps and camp registrations (staff only).

## Tests and checks

```powershell
python manage.py check
python manage.py test
```

51 automated tests cover compatibility, matching filters, lifecycle validation, response
permissions, capacity, duplicate protection, check-in, verification, certificates, achievements,
exports, authentication, role permissions, privacy and notification preferences.

## Privacy and security notes

- Role and object level checks on dashboards, requests, certificates and check-in.
- Donor phone numbers stay hidden unless the donor publishes them or responds to a request.
- CSRF protection on every form, password hashing through Django, password validators enabled.
- Certificates and exports are access controlled; QR tokens are random UUIDs and staff-only.
- Demo mode is tied to `DEBUG`; the seeder will not run against a production configuration.

## Known limitations

- Compatibility is preliminary red-cell guidance, not medical approval for transfusion.
- Notifications are in-app only (the email backend prints to the console in development).
- Pagination and filters are server-side; no client-side SPA behaviour.
- SQLite is used for a local demonstration; a production deployment would move to PostgreSQL,
  add WhiteNoise or a web server for static files, and set real secrets.
