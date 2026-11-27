"""Sample enquiries for every form, to see how the admin and dashboard look with data.

    python manage.py demo_enquiries            # add the samples
    python manage.py demo_enquiries --remove   # remove them again

Samples use email addresses ending in @demo.example.com (that's how --remove finds them). They are never
sent to Airtable and no emails go out. Real enquiries are never touched. Meant for your own computer or
a test copy; on the live site the samples would show to all staff until removed.
"""

import random
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

from core.airtable import DEMO_EMAIL_DOMAIN
from core.models import AIRTABLE_OFF, CandidateRegistration, ContactEnquiry, VacancyEnquiry

CANDIDATES = [
    # name, phone, location, visa, preferred, industry, position, types, experience, support, package, status
    ("Aisha Rahman", "0412 345 901", "Perth, WA", "Student Visa (Subclass 500)", "Perth Metro",
     "Aged Care & Disability", "Personal care assistant", ["Part - Time", "Casual"], "1–3 Years",
     ["jobs"], "", "new"),
    ("Liam O'Connor", "0423 118 274", "Joondalup, WA", "Australian Citizen", "Northern suburbs",
     "Construction & Trades", "Forklift operator\nWarehouse hand", ["Full Time"], "3–5 Years",
     ["jobs", "resume"], "basic", "contacted"),
    ("Priya Sharma", "0431 552 019", "Melbourne, VIC", "Temporary Graduate Visa (Subclass 485)", "Perth CBD",
     "Healthcare & Nursing", "Registered nurse", ["Full Time"], "More than 5 Years",
     ["jobs", "interview"], "", "active"),
    ("Tenzin Dorji", "0447 903 662", "Kathmandu, Nepal", "Offshore Applicant / Unsure", "Anywhere in WA",
     "Hospitality & Tourism", "Chef de partie\nCook", ["Full Time", "Temporary / Contract"], "3–5 Years",
     ["jobs"], "", "new"),
    ("Grace Nguyen", "0458 210 337", "Fremantle, WA", "Australian Permanent Resident", "Fremantle",
     "Administration & Office", "Receptionist\nOffice administrator", ["Part - Time"], "1–3 Years",
     ["resume", "career"], "professional", "placed"),
    ("Mateo Silva", "0469 774 120", "Rockingham, WA", "Working Holiday / Work and Holiday Visa (417/462)",
     "Rockingham", "Cleaning & Maintenance", "Commercial cleaner", ["Casual", "Flexible"], "Less than 1 Year",
     ["jobs"], "", "closed"),
    ("Hannah Wilson", "0470 336 845", "Bunbury, WA", "Australian Citizen", "South West",
     "Retail & Warehousing", "Store supervisor", ["Full Time"], "3–5 Years",
     ["jobs", "interview"], "", "contacted"),
    ("Sonam Choden", "0481 902 556", "Canberra, ACT", "Skilled Visa (189/190/491)", "Perth Metro",
     "Aged Care & Disability", "Disability support worker", ["Part - Time", "Casual"], "No Experience",
     ["jobs", "resume"], "criteria", "new"),
]

VACANCIES = [
    # company, industry, contact, phone, position, types, count, location, details, status
    ("Swan River Aged Care", "Aged Care & Disability", "Megan Hart", "0892 114 300", "Personal care workers",
     ["Part - Time", "Casual"], "2-5", "Bayswater, WA", "Cert III in Individual Support required. Weekend shifts.",
     "new"),
    ("Harbour Kitchen Co.", "Hospitality", "Daniel Kim", "0412 908 551", "Sous chef",
     ["Full Time"], "1", "Fremantle, WA", "Sponsorship possible for the right person.", "contacted"),
    ("Westline Logistics", "Retail & Warehousing", "Rachel Moore", "0433 671 208", "Forklift drivers",
     ["Full Time", "Temporary / Contract"], "6-10", "Kewdale, WA", "LF licence and own transport.", "recruiting"),
    ("Coastal Medical Centre", "Healthcare", "Dr Ian Patel", "0894 302 177", "Practice nurse",
     ["Part - Time"], "1", "Scarborough, WA", "", "placed"),
    ("BuildRight Constructions", "Construction & Trades", "Tom Becker", "0421 449 803", "Carpenters",
     ["Full Time"], "2-5", "Baldivis, WA", "White card essential.", "new"),
    ("Northside Office Group", "Administration & Office", "Lisa Tran", "0438 115 760", "Office administrator",
     ["Full Time"], "1", "Osborne Park, WA", "", "closed"),
]

GENERAL = [
    # name, phone, type, message, status
    ("Olivia Brown", "0415 220 984", "employer",
     "Hi, we run three cafes in Perth and need casual baristas for summer. What are your fees?", "new"),
    ("Karma Wangmo", "0446 781 233", "candidate",
     "I sent my registration last week. Is there anything else you need from me?", "contacted"),
    ("Steve Mitchell", "", "other",
     "Do you also help with visa sponsorship paperwork for employers?", "new"),
    ("Jessica Lee", "0478 663 102", "candidate",
     "Can I book a resume review this Thursday afternoon?", "closed"),
]


def _email(name):
    first = name.split()[0].lower().replace("'", "")
    return f"{first}.{random.randint(10, 99)}{DEMO_EMAIL_DOMAIN}"


class Command(BaseCommand):
    help = "Add sample enquiries for every form (or remove them with --remove)."

    def add_arguments(self, parser):
        parser.add_argument("--remove", action="store_true", help="Remove the sample enquiries.")

    def handle(self, *args, **opts):
        models = (CandidateRegistration, VacancyEnquiry, ContactEnquiry)
        if opts["remove"]:
            total = sum(m.objects.filter(email__iendswith=DEMO_EMAIL_DOMAIN).delete()[0] for m in models)
            self.stdout.write(self.style.SUCCESS(f"Removed {total} sample enquiries."))
            return

        staff = list(get_user_model().objects.filter(is_staff=True, is_active=True))
        now = timezone.now()

        def finish(obj, status, days):
            """Received some days ago; anything past New belongs to a staff member, like real use."""
            owner = random.choice(staff) if staff and status != "new" else None
            notes = "" if status == "new" else random.choice(
                ["Called, will send more details.", "Left a voicemail.", "Good fit, following up next week.", ""])
            when = now - timedelta(days=days, hours=random.randint(0, 9), minutes=random.randint(0, 59))
            type(obj).objects.filter(pk=obj.pk).update(created_at=when, assigned_to=owner, notes=notes)

        made = 0
        for i, (name, phone, loc, visa, pref, ind, pos, types, exp, support, package, status) in enumerate(CANDIDATES):
            obj = CandidateRegistration.objects.create(
                full_name=name, phone=phone, email=_email(name), location=loc, visa_type=visa,
                preferred_location=pref, industry=ind, position_sought=pos, employment_types=types,
                experience=exp, resume_package=package, criteria_count=3 if package == "criteria" else None,
                preferred_times="Weekday mornings" if "interview" in support or "career" in support else "",
                consent=True, status=status, airtable_status=AIRTABLE_OFF,
                **{f"support_{key}": True for key in support})
            finish(obj, status, days=i * 2)
            made += 1
        for i, (company, ind, contact, phone, pos, types, count, loc, details, status) in enumerate(VACANCIES):
            obj = VacancyEnquiry.objects.create(
                company=company, industry=ind, contact_name=contact, phone=phone, email=_email(contact),
                position=pos, employment_types=types, positions_count=count, location=loc, details=details,
                consent=True, status=status, airtable_status=AIRTABLE_OFF)
            finish(obj, status, days=i * 3 + 1)
            made += 1
        for i, (name, phone, kind, message, status) in enumerate(GENERAL):
            obj = ContactEnquiry.objects.create(name=name, email=_email(name), phone=phone,
                                                enquirer_type=kind, message=message, status=status)
            finish(obj, status, days=i * 4)
            made += 1
        self.stdout.write(self.style.SUCCESS(
            f"Added {made} sample enquiries ({len(CANDIDATES)} candidates, {len(VACANCIES)} vacancies, "
            f"{len(GENERAL)} general). Remove them with: python manage.py demo_enquiries --remove"))
