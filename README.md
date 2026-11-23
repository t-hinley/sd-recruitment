# SD Recruitment website

*Match Talent, Drive Success.*

A clean, simple website for SD Recruitment that sends visitors down one of two paths, **Employers**
or **Candidates**. It is built from three documents: the *Website Amendment Recommendation*, the
*Employer Page Content* and the *Candidate Website Content*.

Built with Django (Python), the same stack as the SD Commercial website, so it deploys and is managed
the same way.

## Pages

| Page | What's on it |
|---|---|
| **Home** `/` | "Connecting Talent with Opportunity.", a short intro, the **For Employers** and **For Candidates** buttons (visible without scrolling, also on phones), three highlights, the two audience cards, a brief summary of services and a contact prompt. |
| **About Us** `/about/` | Company profile, recruitment approach (4 steps), values and industries. |
| **Employers** `/employers/` | "Find the Right People for Your Business.", why use a recruitment agency (6 benefits), the industries grid, the 5-step process and the **Submit a Vacancy** form. The button is at the top and the form is at the bottom. |
| **Candidates** `/candidates/` | "Your Next Opportunity Starts Here.", why work with a recruiter (5 benefits), 3 career support cards, current opportunities, what happens after registering, and the **Register Your Interest** form with an optional CV upload. |
| **Contact Us** `/contact/` | Contact details and a short general enquiry form. |
| **Privacy Policy** `/privacy/` | The privacy notice that the candidate consent tick box links to. |

### Forms and Airtable
The two main forms use the same fields, options and required fields as the SD Recruitment Airtable
forms:

| Website form | Airtable form |
|---|---|
| **Submit a Vacancy** (Employers page) | *SD Recruitment, Employer Enquiry Form* |
| **Register Your Interest** (Candidates page) | *SD Recruitment, Talent Registration Form* |

The Candidates form also has the items the Candidate Website Content document asked for, which aren't
in the Airtable form: *What can we help with?* (job opportunities, resume support, interview
preparation, career counselling), the optional CV upload and the consent tick box.

Each submission is saved on the website first, then copied to Airtable, into the same table the Airtable
forms use (`core/airtable.py`). Fields are matched by their Airtable field ID, so renaming a column in
Airtable doesn't break the copy. If Airtable can't be reached, the visitor still sees "Thank you", the
record shows **Failed** in the admin, and it is sent again by the admin action *Send selected to
Airtable again* or by `manage.py sync_airtable`. Contact Us messages stay on the website only.

To switch it on, put an Airtable personal access token in `.env` as `AIRTABLE_TOKEN`. It needs the
`data.records:write` scope and access to the SD Recruitment base only.

### Behaviour the documents asked for
- **Service buttons pre-select the form.** *Get resume support*, *Prepare for an interview* and
  *Explore career support* open the same candidate form with that service already ticked
  (`/candidates/?service=resume|interview|career`). The main *Register your interest* button opens
  it with nothing ticked.
- **CV upload is optional.** Accepts PDF, Word, RTF, ODT or TXT files up to 5 MB, and checks that the
  file really is a document.
- **Consent is required** before a candidate can register, with a link to the Privacy Policy.
- **No promises of placement.** The site says that registering doesn't guarantee an interview, offer
  or placement, and the vacancy form makes no guarantees either.
- **"Candidates" is used everywhere, never "Jobseekers".**
- **Industry cards on the Employers page** open the vacancy form with that industry selected.
- **Brand colours:** Logo Orange `#ED5A2A`, Logo Blue `#304B98`, white and light grey `#F3F5F8`. Blue
  is used for headings and primary buttons, orange for highlights. Orange buttons use a slightly
  deeper `#C84414` so the white text meets accessibility contrast.
- The site has no carousels, pop-ups or decorative animation. It uses the Inter font.

## Admin (`/admin/`)

The admin has the same design as the other SD admins. It includes:
- **Dashboard:** new candidates, vacancies and messages; status charts; activity by industry; which
  support candidates asked for; and the latest submissions.
- **Candidates, Vacancies, Contact enquiries.** What the visitor submitted is read-only. Staff
  update the status, *Assigned to* and internal notes. Candidate records have a **Download CV**
  button.
- **Current opportunities:** add, edit or hide the jobs shown on the Candidates page. Each job gets
  an *Apply* button that opens the form linked to that job.
- **Airtable status** on each vacancy and candidate (Sent, Failed or Not set up), with a *send again* action.
- **Reports:** CSV exports for administrators.
- **Roles:** *Administrators* have full access. *Staff* (the "Staff" group) can work on records and
  manage jobs, but can't delete records, export reports or manage users.
- Email notifications for each new submission. CVs are never emailed.

### Privacy of CVs
CVs are stored in `private_media/resumes/` under random file names. The web server does not serve
that folder, so a CV can only be downloaded by signed-in staff through the admin. Deleting a
candidate also deletes their CV file.

## Editing content
- **Wording, benefits, industries, steps and service cards:** `core/content.py`
- **Contact details** (phone, email, address, hours, LinkedIn): set them in `.env`. See
  `.env.example`. Anything left empty is hidden.
- **Logo:** `static/images/` (made from the supplied SD Recruitment logo artwork).

## Run it locally

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python manage.py migrate
.venv/bin/python manage.py createsuperuser
.venv/bin/python manage.py runserver
```

Open http://127.0.0.1:8000. Locally, emails are printed in the terminal.

Run the tests:

```bash
.venv/bin/python manage.py test
```

## Deploying
See **[DEPLOY_VPS.md](DEPLOY_VPS.md)** for the GoDaddy VPS (Nginx + Gunicorn), set up next to the
existing SD sites without changing them. `passenger_wsgi.py` is included if cPanel is used instead.
