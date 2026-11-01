"""Editorial copy that is reused across the public pages."""

HOW_IT_WORKS = [
    {
        "title": "Register with your role",
        "body": "Donors record their blood group, city and availability. Recipients record who needs the blood and where.",
        "icon": "bi-person-vcard",
    },
    {
        "title": "Raise or find a request",
        "body": "A request carries the blood group, units needed, hospital and date. Donors see the compatible requests in their city.",
        "icon": "bi-clipboard2-pulse",
    },
    {
        "title": "Match and coordinate",
        "body": "Every donor listed against a request carries the reason they match. Donors respond, recipients confirm.",
        "icon": "bi-people",
    },
    {
        "title": "Donate, verify, get certified",
        "body": "The donation is recorded at the hospital or camp. An administrator verifies it, then the certificate and achievements unlock.",
        "icon": "bi-patch-check",
    },
]

WHY_LIFELINK = [
    {
        "title": "Matching you can check",
        "body": "Each suggested donor shows why they appear: red-cell compatibility, city, availability and the 90-day eligibility gap.",
        "icon": "bi-diagram-3",
    },
    {
        "title": "Emergency requests kept separate",
        "body": "Emergency requests get their own queue and reach matching donors immediately, so routine requests are not buried.",
        "icon": "bi-exclamation-octagon",
    },
    {
        "title": "Verified donations only",
        "body": "Nothing counts until an administrator verifies the record. Certificates are issued from verified data alone.",
        "icon": "bi-shield-check",
    },
    {
        "title": "Camps with real check-in",
        "body": "Register for a camp, carry a QR ticket, and get checked in at the desk. Capacity and duplicate registrations are enforced.",
        "icon": "bi-qr-code",
    },
]

AWARENESS_FACTS = [
    {
        "stat": "90 days",
        "title": "Gap between whole-blood donations",
        "body": "A healthy adult can donate whole blood once every 90 days. LifeLink blocks a donor from matching until the gap has passed.",
    },
    {
        "stat": "8-10 min",
        "title": "Time the donation itself takes",
        "body": "Registration, screening and refreshments take the appointment to about 45 minutes in total.",
    },
    {
        "stat": "3 patients",
        "title": "Patients served by one donation",
        "body": "A single unit is separated into red cells, plasma and platelets, so one donation can support more than one patient.",
    },
    {
        "stat": "O-",
        "title": "The group used in emergencies",
        "body": "O negative red cells can be given to every blood group when there is no time to crossmatch.",
    },
]

FAQ_ITEMS = [
    {
        "q": "Who can donate blood?",
        "a": "Healthy adults between 18 and 65 years who weigh at least 50 kg, have no fever or infection in the past two weeks and have not donated whole blood in the last 90 days. The final decision always rests with the medical team at the donation centre.",
    },
    {
        "q": "Does LifeLink guarantee a matching donor?",
        "a": "No. LifeLink shows preliminary red-cell compatibility so you know whom to approach. Crossmatching and medical screening at the hospital decide whether a transfusion can happen.",
    },
    {
        "q": "Is my phone number shown to everyone?",
        "a": "No. Donor phone numbers are hidden by default. A donor can choose to publish a contact number on their card, otherwise contact details are shared only with the recipient of a request the donor has responded to.",
    },
    {
        "q": "How do I get a donation certificate?",
        "a": "The donation is recorded when you donate at a camp or hospital. Once an administrator verifies the record, the certificate appears in your dashboard with a reference number that anyone can check.",
    },
    {
        "q": "What happens to an emergency request?",
        "a": "It is marked as an emergency across the platform and matching donors in that city are notified immediately. Administrators see emergency requests in a separate monitoring queue.",
    },
    {
        "q": "Can I cancel a camp registration?",
        "a": "Yes, from your camp ticket page any time before registration closes. The slot is released back to the camp so another donor can take it.",
    },
]

CONTACT_DETAILS = {
    "phone": "+91 172 400 1120",
    "email": "hello@lifelink.org",
    "address": "Level 2, Sector 17 Plaza, Chandigarh 160017",
    "hours": "Monday to Saturday, 9:00 to 18:00",
}

DEMO_ACCOUNTS = [
    {
        "role": "Administrator",
        "username": "admin",
        "password": "LifeLink@2026",
        "name": "Dr. Meera Sethi",
        "note": "Full console: users, requests, donation verification, camps, analytics.",
        "icon": "bi-shield-lock",
    },
    {
        "role": "Donor",
        "username": "priya.donor",
        "password": "LifeLink@2026",
        "name": "Priya Sharma",
        "note": "Donor in Ludhiana with verified donations, camp tickets and achievements.",
        "icon": "bi-droplet",
    },
    {
        "role": "Recipient",
        "username": "rahul.recipient",
        "password": "LifeLink@2026",
        "name": "Rahul Verma",
        "note": "Recipient coordinating an active request at a Jalandhar hospital.",
        "icon": "bi-person-heart",
    },
]

MEDICAL_DISCLAIMER = (
    "Blood group compatibility shown by LifeLink is preliminary educational guidance "
    "for red blood cell compatibility. It is not medical approval for transfusion. "
    "Professional medical assessment and crossmatching are required."
)
