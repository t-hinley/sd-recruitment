"""Site content and business details in one place, so updates are easy.

Wording comes from the SD Recruitment website documents (Website Amendment Recommendation,
Employer Page Content and Candidate Website Content).
"""

import os
import re

_PHONE = os.environ.get("BUSINESS_PHONE", "").strip()

# Contact details. Fill these in (or set them in .env) before going live. Anything left empty
# is simply not shown on the site.
BUSINESS = {
    "name": "SD Recruitment",
    "tagline": "Match Talent, Drive Success.",
    "phone_display": _PHONE,
    "phone_tel": re.sub(r"[^0-9+]", "", _PHONE),
    "email": os.environ.get("BUSINESS_EMAIL", ""),
    "address": os.environ.get("BUSINESS_ADDRESS", ""),
    "hours": os.environ.get("BUSINESS_HOURS", "Monday to Friday, 9:00 am – 5:00 pm"),
    "service_area": os.environ.get("BUSINESS_SERVICE_AREA", "Australia"),
}

# Icons reference symbols defined in templates/includes/icons.html

# ---- Home --------------------------------------------------------------------------------
HOME_HIGHLIGHTS = [
    ("award", "Quality Talent"),
    ("dartboard", "Role Fit & Cultural Match"),
    ("users", "Long-Term Partnerships"),
]

HOME_SERVICES = [
    ("search", "Talent sourcing",
     "We reach candidates through job boards, professional networks, referrals and direct sourcing."),
    ("clipboard", "Candidate screening",
     "Applications are reviewed and assessed against your role requirements before you see a shortlist."),
    ("briefcase", "Permanent recruitment",
     "Support to find the right people for ongoing roles in your business."),
    ("compass", "Career support",
     "Resume support, interview preparation and career counselling for candidates."),
]

# ---- About -------------------------------------------------------------------------------
ABOUT_APPROACH = [
    ("Listen first", "We start by understanding the role, the team and what success looks like for you."),
    ("Screen carefully", "We assess experience and fit against your brief, so you only see relevant candidates."),
    ("Communicate clearly", "Employers and candidates know where things stand at every stage."),
    ("Support to placement", "We stay involved from the first conversation through to the agreed start date."),
]

ABOUT_VALUES = [
    ("shield", "Integrity", "Honest advice and realistic expectations for employers and candidates."),
    ("users", "Respect", "Every candidate and client is treated professionally and with care."),
    ("dartboard", "Quality", "A focus on the right match rather than the most applications."),
    ("link", "Partnership", "Relationships that continue well beyond a single vacancy."),
]

# ---- Employers -----------------------------------------------------------------------------
EMPLOYER_BENEFITS = [
    ("clock", "Save time",
     "We manage key parts of the recruitment process, from advertising and sourcing to shortlisting, "
     "so your team can focus on running the business."),
    ("network", "Reach more candidates",
     "We use job boards, professional networks, referrals and direct sourcing to connect with people "
     "who may not be actively applying."),
    ("clipboard", "Better candidate screening",
     "We review applications and assess candidates against the role requirements before presenting a shortlist."),
    ("chart", "Industry and market insight",
     "Practical feedback on candidate availability, role requirements and market expectations."),
    ("route", "A more efficient hiring process",
     "We coordinate communication, interviews and feedback to keep recruitment organised and moving."),
    ("check-circle", "Support through to placement",
     "We coordinate the process between employer and candidate, from initial brief through to offer and placement."),
]

# slug -> (icon, title, examples). The slugs are also the choices on the forms.
INDUSTRIES = [
    ("healthcare", "heart", "Healthcare & Support Services",
     "Clinical, allied health, medical administration and aged care roles."),
    ("hospitality", "store", "Hospitality, Retail & Administration",
     "Retail managers, restaurant and café managers, chefs and administration roles."),
    ("construction", "hardhat", "Engineering, Construction & Trades",
     "Construction, project support, site-based and trade-related positions."),
    ("education", "school", "Education & Early Childhood",
     "Early learning, education support and centre-based roles."),
]

EMPLOYER_PROCESS = [
    ("Understand your vacancy", "We discuss the role, requirements, experience and timeframe."),
    ("Source and screen", "We search for suitable candidates and assess their experience against your brief."),
    ("Present a shortlist", "We share relevant candidate profiles for your consideration."),
    ("Coordinate interviews and offers", "We help manage communication and next steps."),
    ("Placement", "We support the process through to the agreed commencement."),
]

# ---- Candidates ----------------------------------------------------------------------------
CANDIDATE_BENEFITS = [
    ("door", "Access to opportunities",
     "Hear about suitable vacancies, including roles that may not be widely advertised."),
    ("route", "Guidance throughout the process",
     "Get support with applications, interview arrangements and communication with employers."),
    ("dartboard", "A better match",
     "Discuss your skills, experience and preferences so we can consider roles that align with your goals."),
    ("chat", "Career advice and feedback",
     "Receive practical guidance to help you present your experience and prepare for opportunities."),
    ("user", "A professional point of contact",
     "Have someone to communicate with and ask questions during the recruitment process."),
]

# slug matches CandidateRegistration support choices; used for ?service=<slug> on the form.
CAREER_SERVICES = [
    ("resume", "file", "Resume Support",
     "Get help creating or improving your resume so your skills, experience and achievements are clearly presented.",
     "Get resume support"),
    ("interview", "mic", "Interview Preparation",
     "Build confidence and prepare for interviews with practical guidance on common questions and how to "
     "present your experience.",
     "Prepare for an interview"),
    ("career", "compass", "Career Counselling",
     "Discuss your career goals, strengths and possible pathways to help plan your next career move.",
     "Explore career support"),
]

CANDIDATE_PROCESS = [
    ("Register your interest", "Tell us about your experience, the work you want and any support you need."),
    ("Talk with us", "We get in touch to understand your goals and answer your questions."),
    ("Get matched", "When a suitable role comes up, we discuss it with you before putting you forward."),
    ("Interview and next steps", "We help arrange interviews and keep you informed through to an outcome."),
]
