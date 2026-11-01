"""Create repeatable demonstration data for LifeLink.

The command never deletes records and never overwrites an existing account. Running it
twice produces the same dataset, so it is safe to use before a demonstration.

    python manage.py seed_demo
"""

from datetime import date, datetime, time, timedelta

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from accounts.models import DonorProfile, RecipientProfile, User, VolunteerProfile
from blood.matching import find_matching_donors
from blood.models import BloodRequest, DonorResponse, RequestStatusEvent
from blood.services import LIFECYCLE_CHAIN, notify_matching_donors
from camps.models import CampFeedback, CampRegistration, DonationCamp, VolunteerAssignment
from donations.models import DonationRecord
from donations.services import (
    award_achievements,
    ensure_achievement_catalogue,
    record_donation,
)
from notifications.models import Notification
from notifications.services import notify

DEMO_PASSWORD = "LifeLink@2026"
AVATAR = "https://i.pravatar.cc/120?u="

ADMIN = {
    "username": "admin",
    "first_name": "Meera",
    "last_name": "Sethi",
    "email": "admin@lifelink.local",
    "city": "Chandigarh",
    "phone": "98765 40000",
}

# username, first, last, city, blood group, gender, dob, weight, phone, verified, last donation (days ago)
DONORS = [
    ("priya.donor", "Priya", "Sharma", "Ludhiana", "A+", "female", "1996-04-12", 58, "98765 41001", True, 165),
    ("arjun.donor", "Arjun", "Mehta", "Chandigarh", "O-", "male", "1992-09-03", 74, "98765 41002", True, 235),
    ("simran.donor", "Simran", "Kaur", "Jalandhar", "B+", "female", "1999-01-22", 55, "98765 41003", True, 110),
    ("rohan.donor", "Rohan", "Kapoor", "Ludhiana", "O+", "male", "1994-06-30", 70, "98765 41004", True, None),
    ("neha.donor", "Neha", "Verma", "Amritsar", "AB+", "female", "1997-11-05", 52, "98765 41005", True, 153),
    ("vikram.donor", "Vikram", "Singh", "Phagwara", "A-", "male", "1989-02-18", 80, "98765 41006", True, 213),
    ("ananya.donor", "Ananya", "Iyer", "Chandigarh", "B-", "female", "2000-07-09", 54, "98765 41007", False, None),
    ("karan.donor", "Karan", "Malhotra", "Delhi", "A+", "male", "1995-12-12", 76, "98765 41008", True, 104),
    ("ishita.donor", "Ishita", "Rao", "Jalandhar", "O+", "female", "1998-03-27", 53, "98765 41009", True, 260),
    ("aditya.donor", "Aditya", "Nair", "Amritsar", "AB-", "male", "1991-08-08", 72, "98765 41010", True, None),
    ("meghna.donor", "Meghna", "Bose", "Ludhiana", "B+", "female", "1996-10-19", 51, "98765 41011", True, 61),
    ("sanjay.donor", "Sanjay", "Gill", "Delhi", "O-", "male", "1987-05-04", 82, "98765 41012", True, 275),
    ("pooja.donor", "Pooja", "Rani", "Amritsar", "A+", "female", "1999-06-16", 50, "98765 41013", True, None),
    ("farhan.donor", "Farhan", "Khan", "Jalandhar", "B-", "male", "1993-04-25", 68, "98765 41014", False, None),
    ("tanvi.donor", "Tanvi", "Joshi", "Chandigarh", "O+", "female", "1997-09-14", 57, "98765 41015", True, 129),
    ("harpreet.donor", "Harpreet", "Sandhu", "Patiala", "AB+", "male", "1990-12-01", 79, "98765 41016", True, 216),
    ("rupinder.donor", "Rupinder", "Pal", "Patiala", "B+", "male", "1994-02-14", 71, "98765 41017", True, None),
]

# username, first, last, city, kind, organisation, phone, verified
RECIPIENTS = [
    ("rahul.recipient", "Rahul", "Verma", "Jalandhar", "family", "", "98765 42001", True),
    ("anjali.recipient", "Anjali", "Gupta", "Ludhiana", "self", "", "98765 42002", True),
    ("mohit.recipient", "Mohit", "Chawla", "Chandigarh", "family", "", "98765 42003", True),
    ("sunita.recipient", "Sunita", "Devi", "Amritsar", "family", "", "98765 42004", False),
    ("naveen.recipient", "Naveen", "Bhalla", "Delhi", "organisation", "City Care Hospital", "98765 42005", True),
    ("kiran.recipient", "Kiran", "Sethi", "Ludhiana", "organisation", "Sahyog Blood Bank", "98765 42006", True),
]

AREAS = {
    "Ludhiana": "Model Town",
    "Chandigarh": "Sector 22",
    "Jalandhar": "Model Town",
    "Amritsar": "Ranjit Avenue",
    "Delhi": "Saket",
    "Phagwara": "GT Road",
    "Patiala": "Leela Bhawan",
    "Mohali": "Phase 3B2",
}

CAMP_IMAGES = [
    (
        "https://images.pexels.com/photos/7156163/pexels-photo-7156163.jpeg?auto=compress&cs=tinysrgb&w=1200",
        "Volunteers managing a community blood donation drive — Gustavo Fring on Pexels",
    ),
    (
        "https://images.pexels.com/photos/37191926/pexels-photo-37191926.jpeg?auto=compress&cs=tinysrgb&w=1200",
        "A donor giving blood at a collection centre — Manuel Camacho-Navarro on Pexels",
    ),
    (
        "https://images.pexels.com/photos/6646916/pexels-photo-6646916.jpeg?auto=compress&cs=tinysrgb&w=1200",
        "Volunteers setting up a blood donation camp hall — RDNE Stock project on Pexels",
    ),
    (
        "https://images.pexels.com/photos/6129682/pexels-photo-6129682.jpeg?auto=compress&cs=tinysrgb&w=1200",
        "A nurse checks a blood donation bag at a hospital camp — RDNE Stock project on Pexels",
    ),
]

CAMPS = [
    {
        "title": "Sector 17 Community Blood Drive",
        "organizer": "LifeLink Foundation with PGIMER",
        "city": "Chandigarh",
        "venue": "Sector 17 Plaza, Community Hall",
        "address": "Plaza Level 1, Sector 17",
        "pincode": "160017",
        "day_offset": 9,
        "start_hour": 10,
        "hours": 6,
        "capacity": 60,
        "phone": "0172 400 1120",
        "image": CAMP_IMAGES[0],
        "description": (
            "A walk-in community drive for whole blood donation. The desk verifies registration, "
            "the medical team screens every donor, and refreshments are served after donation. "
            "Carry a photo ID."
        ),
    },
    {
        "title": "Ludhiana Industrial Blood Camp",
        "organizer": "Sahyog Blood Bank",
        "city": "Ludhiana",
        "venue": "Chamber of Commerce Hall, Focal Point",
        "address": "Phase 5, Focal Point Industrial Area",
        "pincode": "141010",
        "day_offset": 18,
        "start_hour": 9,
        "hours": 7,
        "capacity": 45,
        "phone": "0161 400 2210",
        "image": CAMP_IMAGES[1],
        "description": (
            "Organised with local factories so donors can donate before their shift. Forty five "
            "slots, appointment held by registration only."
        ),
    },
    {
        "title": "Jalandhar College Donation Drive",
        "organizer": "LifeLink with Civil Hospital Jalandhar",
        "city": "Jalandhar",
        "venue": "Lyallpur Khalsa College, Auditorium",
        "address": "GT Road, Jalandhar",
        "pincode": "144001",
        "day_offset": 27,
        "start_hour": 10,
        "hours": 6,
        "capacity": 80,
        "phone": "0181 400 3310",
        "image": CAMP_IMAGES[2],
        "description": (
            "Student-led drive with an awareness stall on eligibility, iron-rich diet and the 90-day "
            "gap. Volunteers from the NSS unit assist at the desk."
        ),
    },
    {
        "title": "Amritsar Winter Blood Camp",
        "organizer": "Guru Nanak Dev Hospital",
        "city": "Amritsar",
        "venue": "Guru Nanak Dev Hospital, Block B",
        "address": "Majitha Road",
        "pincode": "143001",
        "day_offset": -24,
        "start_hour": 9,
        "hours": 6,
        "capacity": 50,
        "phone": "0183 400 4410",
        "image": CAMP_IMAGES[3],
        "description": (
            "The winter collection camp that ran last month. Attendance was recorded at the desk and "
            "feedback is open to registered attendees."
        ),
    },
]

# recipient, patient, age, group, units, hospital, address, city, pincode, days_ahead,
# urgency, status, units_fulfilled, notes, responses
REQUESTS = [
    {
        "recipient": "rahul.recipient",
        "patient": "Harleen Kaur", "age": 34, "group": "A+", "units": 2,
        "hospital": "DMC Hospital", "address": "Tagore Nagar, Ludhiana",
        "city": "Ludhiana", "pincode": "141001", "days_ahead": 1,
        "urgency": "emergency", "status": "responses", "fulfilled": 0,
        "notes": "Post-operative requirement in surgical ICU, bed 12. Doctor advised two units.",
        "responses": [
            ("priya.donor", "interested", "I am in Ludhiana and can reach DMC by 9 am."),
            ("karan.donor", "interested", "Travelling from Delhi tonight, available tomorrow morning."),
        ],
    },
    {
        "recipient": "mohit.recipient",
        "patient": "Devansh Chawla", "age": 9, "group": "O-", "units": 1,
        "hospital": "PGIMER", "address": "Sector 12, Nehru Hospital",
        "city": "Chandigarh", "pincode": "160012", "days_ahead": 1,
        "urgency": "emergency", "status": "potential", "fulfilled": 0,
        "notes": "Paediatric thalassaemia transfusion. O negative required.",
        "responses": [],
    },
    {
        "recipient": "anjali.recipient",
        "patient": "Sunita Yadav", "age": 46, "group": "B+", "units": 3,
        "hospital": "Chattanbir Hospital", "address": "Basant Vihar, Jalandhar",
        "city": "Jalandhar", "pincode": "144001", "days_ahead": 2,
        "urgency": "urgent", "status": "coordination", "fulfilled": 0,
        "notes": "Surgery scheduled in two days. Blood bank has one unit only.",
        "responses": [
            ("simran.donor", "confirmed", "Confirmed for tomorrow, 10 am at the blood bank."),
        ],
    },
    {
        "recipient": "kiran.recipient",
        "patient": "Balbir Singh", "age": 58, "group": "AB+", "units": 1,
        "hospital": "Sahyog Blood Bank", "address": "Civil Lines, Ludhiana",
        "city": "Ludhiana", "pincode": "141001", "days_ahead": 4,
        "urgency": "normal", "status": "potential", "fulfilled": 0,
        "notes": "Routine replacement for the blood bank reserve.",
        "responses": [],
    },
    {
        "recipient": "naveen.recipient",
        "patient": "Ritu Malhotra", "age": 27, "group": "O+", "units": 1,
        "hospital": "AIIMS", "address": "Ansari Nagar",
        "city": "Delhi", "pincode": "110029", "days_ahead": 3,
        "urgency": "urgent", "status": "fulfilled", "fulfilled": 1,
        "notes": "Anaemia management with transfusion. One unit received.",
        "responses": [
            ("ishita.donor", "completed", "Donated at AIIMS on the scheduled day."),
        ],
    },
    {
        "recipient": "sunita.recipient",
        "patient": "Gurmeet Kaur", "age": 52, "group": "A-", "units": 1,
        "hospital": "Guru Nanak Dev Hospital", "address": "Majitha Road, Amritsar",
        "city": "Amritsar", "pincode": "143001", "days_ahead": 6,
        "urgency": "normal", "status": "cancelled", "fulfilled": 0,
        "notes": "Cancelled after the hospital arranged units internally.",
        "responses": [],
    },
    {
        "recipient": "rahul.recipient",
        "patient": "Manpreet Singh", "age": 41, "group": "B-", "units": 1,
        "hospital": "Apollo Hospital", "address": "Focal Point, Ludhiana",
        "city": "Ludhiana", "pincode": "141010", "days_ahead": 5,
        "urgency": "normal", "status": "responses", "fulfilled": 0,
        "notes": "Elective surgery requirement, one unit kept ready.",
        "responses": [
            ("farhan.donor", "interested", "B negative donor, can come on Saturday."),
            ("ananya.donor", "interested", "Available on Saturday as well."),
        ],
    },
    {
        "recipient": "kiran.recipient",
        "patient": "Kavita Sharma", "age": 30, "group": "O+", "units": 2,
        "hospital": "Fortis Hospital", "address": "Sector 62, Mohali",
        "city": "Mohali", "pincode": "160062", "days_ahead": 7,
        "urgency": "normal", "status": "responses", "fulfilled": 0,
        "notes": "Two units for a planned caesarean section.",
        "responses": [
            ("rohan.donor", "interested", "First time donor, available any day next week."),
        ],
    },
    {
        "recipient": "mohit.recipient",
        "patient": "Vihaan Mittal", "age": 4, "group": "AB-", "units": 1,
        "hospital": "Amandeep Hospital", "address": "Lawrence Road, Amritsar",
        "city": "Amritsar", "pincode": "143001", "days_ahead": 1,
        "urgency": "emergency", "status": "coordination", "fulfilled": 0,
        "notes": "AB negative is rare in the hospital bank. Paediatric ICU.",
        "responses": [
            ("aditya.donor", "confirmed", "Reaching Amandeep in an hour, please keep the form ready."),
        ],
    },
    {
        "recipient": "anjali.recipient",
        "patient": "Sahil Arora", "age": 22, "group": "A+", "units": 1,
        "hospital": "Civil Hospital", "address": "Rakh Bagh, Jalandhar",
        "city": "Jalandhar", "pincode": "144001", "days_ahead": 2,
        "urgency": "normal", "status": "fulfilled", "fulfilled": 1,
        "notes": "Dengue recovery, one unit received and verified.",
        "responses": [
            ("priya.donor", "completed", "Donated at Civil Hospital Jalandhar."),
            ("pooja.donor", "interested", "Could also donate if a second unit is needed."),
        ],
    },
    {
        "recipient": "sunita.recipient",
        "patient": "Bhavna Kapoor", "age": 36, "group": "B+", "units": 2,
        "hospital": "Patel Hospital", "address": "Civil Lines, Patiala",
        "city": "Patiala", "pincode": "147001", "days_ahead": 8,
        "urgency": "normal", "status": "responses", "fulfilled": 0,
        "notes": "Two units before a hysterectomy.",
        "responses": [
            ("rupinder.donor", "interested", "Based in Patiala, can donate at Patel Hospital."),
        ],
    },
    {
        "recipient": "naveen.recipient",
        "patient": "Aarav Sethi", "age": 15, "group": "O-", "units": 2,
        "hospital": "Max Hospital", "address": "Saket",
        "city": "Delhi", "pincode": "110017", "days_ahead": 2,
        "urgency": "emergency", "status": "responses", "fulfilled": 0,
        "notes": "Road accident, two units of O negative needed urgently.",
        "responses": [
            ("sanjay.donor", "interested", "O negative, 20 minutes from Max Saket."),
            ("arjun.donor", "interested", "Can reach by evening if the requirement is still open."),
        ],
    },
]

# donor, days ago, hospital, verified, camp index (or None)
DONATIONS = [
    ("priya.donor", 165, "DMC Hospital, Ludhiana", True, None),
    ("priya.donor", 420, "Civil Hospital, Jalandhar", True, None),
    ("priya.donor", 560, "DMC Hospital, Ludhiana", True, None),
    ("arjun.donor", 235, "PGIMER, Chandigarh", True, None),
    ("arjun.donor", 500, "Sector 17 Community Blood Drive", True, None),
    ("simran.donor", 110, "Chattanbir Hospital, Jalandhar", True, None),
    ("neha.donor", 153, "Fortis Hospital, Amritsar", True, None),
    ("vikram.donor", 213, "Civil Hospital, Phagwara", True, None),
    ("vikram.donor", 380, "Civil Hospital, Phagwara", True, None),
    ("vikram.donor", 560, "Sector 17 Community Blood Drive", True, None),
    ("vikram.donor", 740, "Civil Hospital, Phagwara", True, None),
    ("vikram.donor", 900, "Civil Hospital, Phagwara", True, None),
    ("karan.donor", 104, "AIIMS, Delhi", True, None),
    ("ishita.donor", 260, "Civil Hospital, Jalandhar", True, None),
    ("ishita.donor", 430, "Civil Hospital, Jalandhar", True, None),
    ("sanjay.donor", 275, "Max Hospital, Delhi", True, None),
    ("tanvi.donor", 129, "PGIMER, Chandigarh", True, None),
    ("harpreet.donor", 216, "Patel Hospital, Patiala", True, None),
    ("meghna.donor", 61, "Apollo Hospital, Ludhiana", True, None),
    ("priya.donor", 24, "Amritsar Winter Blood Camp", False, 3),
    ("rohan.donor", 24, "Amritsar Winter Blood Camp", False, 3),
    ("farhan.donor", 3, "Sahyog Blood Bank, Ludhiana", False, None),
]

# camp index, username, status
REGISTRATIONS = [
    (0, "priya.donor", "registered"),
    (0, "tanvi.donor", "registered"),
    (0, "arjun.donor", "registered"),
    (0, "ananya.donor", "registered"),
    (0, "pooja.donor", "cancelled"),
    (1, "priya.donor", "registered"),
    (1, "rohan.donor", "registered"),
    (1, "sanjay.donor", "registered"),
    (1, "rupinder.donor", "registered"),
    (2, "simran.donor", "registered"),
    (2, "ishita.donor", "registered"),
    (2, "neha.donor", "registered"),
    (3, "priya.donor", "attended"),
    (3, "neha.donor", "attended"),
    (3, "aditya.donor", "attended"),
    (3, "vikram.donor", "no_show"),
    (3, "farhan.donor", "checked_in"),
]

# camp index, username, duty, confirmed
VOLUNTEERS = [
    (0, "priya.donor", "registration", True),
    (0, "rohan.donor", "logistics", True),
    (1, "simran.donor", "refreshments", False),
    (3, "tanvi.donor", "awareness", True),
]


class Command(BaseCommand):
    help = "Create the LifeLink demonstration dataset without deleting or overwriting data."

    def add_arguments(self, parser):
        parser.add_argument("--password", default=DEMO_PASSWORD)
        parser.add_argument(
            "--force",
            action="store_true",
            help="Allow the command to run when DEBUG is off (not recommended).",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        if not settings.DEBUG and not options["force"]:
            raise CommandError(
                "seed_demo writes demonstration accounts and should not run with DEBUG off. "
                "Pass --force only on a local machine."
            )

        password = options["password"]
        ensure_achievement_catalogue()

        admin = self._admin(password)
        donors = self._donors(password)
        recipients = self._recipients(password)
        camps = self._camps(admin)
        requests = self._requests(recipients)
        self._responses(requests, donors)
        self._donations(donors, camps)
        self._registrations(camps, donors)
        self._volunteers(camps, donors)
        self._feedback(camps, donors)
        self._notifications(donors, recipients)

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("LifeLink demonstration data is ready."))
        self.stdout.write(f"  Administrator : {admin.username} / {password}")
        self.stdout.write(f"  Donor         : priya.donor / {password}")
        self.stdout.write(f"  Recipient     : rahul.recipient / {password}")
        self.stdout.write("")
        self.stdout.write(f"  Accounts      : {User.objects.count()} total, "
                          f"{DonorProfile.objects.count()} donors, "
                          f"{RecipientProfile.objects.count()} recipients")
        self.stdout.write(f"  Requests      : {BloodRequest.objects.count()} "
                          f"({BloodRequest.objects.open().count()} open)")
        self.stdout.write(f"  Camps         : {DonationCamp.objects.count()} "
                          f"({DonationCamp.objects.upcoming().count()} upcoming)")
        self.stdout.write(f"  Registrations : {CampRegistration.objects.count()}")
        self.stdout.write(f"  Donations     : {DonationRecord.objects.count()} "
                          f"({DonationRecord.objects.filter(verified=True).count()} verified)")
        self.stdout.write(f"  Notifications : {Notification.objects.count()}")
        self.stdout.write("")

    # -- helpers ----------------------------------------------------------
    def _user(self, username, first, last, email, city, phone, role, password, **extra):
        user, created = User.objects.get_or_create(
            username=username,
            defaults={
                "first_name": first,
                "last_name": last,
                "email": email,
                "city": city,
                "phone": phone,
                "role": role,
                "is_demo": True,
                **extra,
            },
        )
        if created:
            user.set_password(password)
            user.save()
        return user

    def _admin(self, password):
        return self._user(
            ADMIN["username"],
            ADMIN["first_name"],
            ADMIN["last_name"],
            ADMIN["email"],
            ADMIN["city"],
            ADMIN["phone"],
            User.Role.ADMIN,
            password,
            is_staff=True,
            is_superuser=True,
        )

    def _donors(self, password):
        donors = {}
        for row in DONORS:
            (username, first, last, city, group, gender, dob, weight, phone,
             verified, last_offset) = row
            user = self._user(
                username, first, last, f"{username}@lifelink.local", city, phone,
                User.Role.DONOR, password,
            )
            last_donation = None
            if last_offset is not None:
                last_donation = date.today() - timedelta(days=last_offset)
            DonorProfile.objects.get_or_create(
                user=user,
                defaults={
                    "blood_group": group,
                    "date_of_birth": dob,
                    "gender": gender,
                    "weight_kg": weight,
                    "city": city,
                    "area": AREAS.get(city, ""),
                    "pincode": "141001",
                    "last_donation_date": last_donation,
                    "is_available": True,
                    "is_verified": verified,
                    "verified_at": timezone.now() if verified else None,
                    "bio": (
                        "Available for whole blood donation on weekends."
                        if verified
                        else "Profile awaiting administrator review."
                    ),
                },
            )
            donors[username] = user
        return donors

    def _recipients(self, password):
        recipients = {}
        for username, first, last, city, kind, organisation, phone, verified in RECIPIENTS:
            user = self._user(
                username, first, last, f"{username}@lifelink.local", city, phone,
                User.Role.RECIPIENT, password,
            )
            RecipientProfile.objects.get_or_create(
                user=user,
                defaults={
                    "kind": kind,
                    "organisation": organisation,
                    "city": city,
                    "address": f"{city}",
                    "pincode": "141001",
                    "is_verified": verified,
                },
            )
            recipients[username] = user
        return recipients

    def _camps(self, admin):
        camps = []
        for index, row in enumerate(CAMPS):
            start_day = timezone.localdate() + timedelta(days=row["day_offset"])
            starts_at = timezone.make_aware(
                datetime.combine(start_day, time(row["start_hour"], 0))
            )
            ends_at = starts_at + timedelta(hours=row["hours"])
            camp, _created = DonationCamp.objects.get_or_create(
                title=row["title"],
                defaults={
                    "organizer": row["organizer"],
                    "description": row["description"],
                    "image_url": row["image"][0],
                    "image_alt": row["image"][1],
                    "venue": row["venue"],
                    "address": row["address"],
                    "city": row["city"],
                    "pincode": row["pincode"],
                    "starts_at": starts_at,
                    "ends_at": ends_at,
                    "capacity": row["capacity"],
                    "registration_deadline": starts_at - timedelta(days=1),
                    "contact_phone": row["phone"],
                    "status": DonationCamp.Status.SCHEDULED,
                    "is_demo": True,
                    "created_by": admin,
                },
            )
            camps.append(camp)
        return camps

    def _requests(self, recipients):
        requests = {}
        for row in REQUESTS:
            recipient = recipients[row["recipient"]]
            blood_request, created = BloodRequest.objects.get_or_create(
                requester=recipient,
                patient_name=row["patient"],
                hospital_name=row["hospital"],
                defaults={
                    "patient_age": row["age"],
                    "blood_group": row["group"],
                    "units_required": row["units"],
                    "units_fulfilled": row["fulfilled"],
                    "hospital_address": row["address"],
                    "city": row["city"],
                    "pincode": row["pincode"],
                    "required_by": date.today() + timedelta(days=row["days_ahead"]),
                    "contact_phone": recipient.phone,
                    "urgency": row["urgency"],
                    "notes": row["notes"],
                    "is_demo": True,
                },
            )
            if created:
                blood_request.status = row["status"]
                blood_request.save(update_fields=["status"])
                self._events(blood_request, recipient, row["status"])

            if row["status"] in BloodRequest.OPEN_STATUSES:
                notify_matching_donors(blood_request)
            requests[row["patient"]] = blood_request
        return requests

    def _events(self, blood_request, actor, final_status):
        if final_status == BloodRequest.Status.CANCELLED:
            chain = LIFECYCLE_CHAIN[:2]
        else:
            chain = LIFECYCLE_CHAIN[: LIFECYCLE_CHAIN.index(final_status) + 1]
        for step in chain:
            RequestStatusEvent.objects.get_or_create(
                request=blood_request,
                status=step,
                defaults={
                    "actor": actor if step == BloodRequest.Status.CREATED else None,
                    "note": "Demonstration record",
                },
            )
        if final_status == BloodRequest.Status.CANCELLED:
            RequestStatusEvent.objects.get_or_create(
                request=blood_request,
                status=BloodRequest.Status.CANCELLED,
                defaults={"actor": actor, "note": "Cancelled by the recipient"},
            )

    def _responses(self, requests, donors):
        for row in REQUESTS:
            blood_request = requests[row["patient"]]
            for username, status, message in row["responses"]:
                donor = donors[username]
                response, created = DonorResponse.objects.get_or_create(
                    request=blood_request,
                    donor=donor,
                    defaults={"status": status, "message": message},
                )
                if created:
                    group = donor.donor_profile.blood_group if donor.donor_profile else "Donor"
                    notify(
                        blood_request.requester,
                        Notification.Kind.RESPONSE,
                        f"{donor.display_name} responded to {blood_request.reference}",
                        f"{group} · {message}",
                        url=blood_request.get_absolute_url(),
                        dedupe_key=f"req{blood_request.pk}-resp-{donor.pk}",
                    )

    def _donations(self, donors, camps):
        for username, days_ago, hospital, verified, camp_index in DONATIONS:
            donor = donors[username]
            camp = camps[camp_index] if camp_index is not None else None
            record = record_donation(
                donor=donor,
                donation_date=date.today() - timedelta(days=days_ago),
                units=1,
                hospital=hospital,
                camp=camp,
                notes="Demonstration donation record",
                verified=verified,
            )
            DonationRecord.objects.filter(pk=record.pk).update(is_demo=True)

        for username in donors:
            if DonationRecord.objects.filter(donor=donors[username]).exists():
                award_achievements(donors[username])

    def _registrations(self, camps, donors):
        for camp_index, username, status in REGISTRATIONS:
            camp = camps[camp_index]
            user = donors[username]
            registration, created = CampRegistration.objects.get_or_create(
                camp=camp,
                user=user,
                defaults={"status": status},
            )
            if created:
                if status in (
                    CampRegistration.Status.CHECKED_IN,
                    CampRegistration.Status.ATTENDED,
                ):
                    registration.checked_in_at = timezone.now()
                    registration.save(update_fields=["checked_in_at"])
                notify(
                    user,
                    Notification.Kind.CAMP,
                    f"Registered for {camp.title}",
                    f"{camp.starts_at:%d %b %Y, %I:%M %p} at {camp.venue}. Your QR ticket is ready.",
                    url=registration.ticket_url,
                    dedupe_key=f"camp{registration.pk}-registered",
                )

    def _volunteers(self, camps, donors):
        for camp_index, username, duty, confirmed in VOLUNTEERS:
            user = donors[username]
            VolunteerProfile.objects.get_or_create(
                user=user,
                defaults={
                    "city": user.city,
                    "phone": user.phone,
                    "motivation": "Helping at camp desks and guiding first-time donors.",
                },
            )
            assignment, created = VolunteerAssignment.objects.get_or_create(
                camp=camps[camp_index],
                volunteer=user,
                defaults={"duty": duty, "is_confirmed": confirmed},
            )
            if created and confirmed:
                award_achievements(user)

    def _feedback(self, camps, donors):
        past_camp = camps[3]
        CampFeedback.objects.update_or_create(
            camp=past_camp,
            user=donors["priya.donor"],
            defaults={
                "rating": 5,
                "comment": (
                    "The desk checked my ticket in less than a minute and the screening was "
                    "explained clearly."
                ),
            },
        )
        CampFeedback.objects.update_or_create(
            camp=past_camp,
            user=donors["neha.donor"],
            defaults={
                "rating": 4,
                "comment": "Good organisation. More drinking water stations would help.",
            },
        )

    def _notifications(self, donors, recipients):
        announcement = notify(
            donors["priya.donor"],
            Notification.Kind.SYSTEM,
            "Welcome to the LifeLink demonstration",
            "Requests, camps and certificates in this account are demonstration records.",
            force=True,
            dedupe_key="demo-welcome-priya",
        )
        if announcement:
            announcement.save()

        for username in ("arjun.donor", "simran.donor", "neha.donor", "tanvi.donor"):
            notify(
                donors[username],
                Notification.Kind.SYSTEM,
                "New camps are open for registration",
                "Three camps across Chandigarh, Ludhiana and Jalandhar are accepting registrations.",
                url="/camps/",
                force=True,
                dedupe_key=f"demo-camp-notice-{username}",
            )

        notify(
            recipients["rahul.recipient"],
            Notification.Kind.SYSTEM,
            "Emergency requests stay visible to administrators",
            "Requests marked emergency appear in a separate monitoring queue in the console.",
            force=True,
            dedupe_key="demo-admin-queue-note",
        )
