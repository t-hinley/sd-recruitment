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
| **Candidates** `/candidates/` | "Your Next Opportunity Starts Here.", why work with a recruiter (5 benefits), 3 career support cards, current opportunities (from the careers page), what happens after registering, and the **Register Your Interest** form with an optional CV upload. |
| **Career Services** `/career-services/` | Resume packages (Student $50, Basic $95, Professional $200, Executive $350, Selection Criteria $35 per criterion), Interview Preparation ($95, 45 minutes) and Career Counselling (first 15 minutes free, follow-up 30 minutes $65), with prices. Every button opens the Candidates page **Register Your Interest** form with that service (and resume package) already chosen. Linked from the Candidates page cards and the footer. |
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

Each submission is saved on the website first, then copied to Airtable (`core/airtable.py`): vacancies to
`AIRTABLE_EMPLOYER_TABLE` and candidates to `AIRTABLE_TALENT_TABLE`. Today both Airtable forms share one
table, where columns are matched by field ID (renaming a column doesn't break the copy). A form moved to
a table of its own is matched by column name, using the Airtable form labels. If Airtable can't be reached, the visitor still sees "Thank you", the
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
- **Career services on candidate records:** the resume package, number of selection criteria and preferred days/times appear on the candidate record, in emails and in reports. No online payment: the team contacts the person to confirm and invoice. These extra details are not sent to Airtable (it has no columns for them).
- **Jobs from Manatal (careers-page.com):** jobs the client posts on their Manatal careers page show automatically under "Roles we're recruiting for" on the Candidates page (pinned jobs first). Each has a **View & Apply** button that opens the job on the client's careers page (https://sd-recruitment.careers-page.com) in a new tab. The list refreshes every 15 minutes (`MANATAL_CACHE_MINUTES`); if careers-page.com is unreachable, the last list is shown. Set the careers page with `MANATAL_CAREERS_PAGE_URL` (default `https://sd-recruitment.careers-page.com`). Code: `core/careers_feed.py`.
- **Airtable status** on each vacancy and candidate (Sent, Failed or Not set up), with a *send again* action.
- **Reports:** CSV (every field, opens in Excel) or PDF (main fields, ready to print or share) for administrators, for any date range.
- **Roles:** *Administrators* have full access. *Staff* (the "Staff" group) can work on records,
  but can't delete records, export reports or manage users.
- Email notifications for each new submission. CVs are never emailed.
- **Candidate copy:** candidates are emailed a copy of their registration (reply-to is the business email). Limited to 5 per hour per connection and 3 per day per address so the form can't be used to email strangers; switch off with `CANDIDATE_CONFIRMATION_EMAILS=False`.

### Privacy of CVs
CVs are stored in `private_media/resumes/` under random file names. The web server does not serve
that folder, so a CV can only be downloaded by signed-in staff through the admin. Deleting a
candidate also deletes their CV file.

## Editing content
- **Wording, benefits, industries, steps, service cards and Career Services prices:** `core/content.py`
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
