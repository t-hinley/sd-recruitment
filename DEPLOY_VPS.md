# Deploying on the GoDaddy VPS (Ubuntu + Nginx), next to SD Travels and SD Recruitment

For the server that already runs SD Travels (and SD Recruitment) with **Nginx on Ubuntu**. SD Recruitment
is added as a separate site: its own folder (`/srv/sdrecruitment`), its own Python environment, its own
Nginx file and its own SSL certificate. **No file of the other sites is changed.**

Example name used below: **`recruitment.example.com.au`**. Replace it everywhere with the real domain
(also in `deploy/nginx-sdrecruitment.conf` before Step 8).

```
visitor ─► Nginx (ports 80/443)
             ├─ SD Travels / SD Recruitment names ─► unchanged
             └─ recruitment.example.com.au       ─► /run/sdrecruitment/gunicorn.sock ─► Django (SD Recruitment)
```

Type commands one block at a time. Lines starting with `#` are explanations, not commands.

---

## Step 0 – Before you start

1. GoDaddy → **Servers → Manage → Snapshots → take a snapshot** (lets you undo everything).
2. DNS (GoDaddy): an `A` record for the domain → the server IP, and a `CNAME` record `www` → the domain.
   Both names must reach the server before Step 9.
3. Log in: `ssh sdadmin@YOUR-SERVER-IP`

## Step 1 – Look before changing anything (read-only)

```bash
nginx -v
ls /etc/nginx/sites-enabled/
python3 --version
free -h
sudo ufw status
```

- `python3 --version` must be **3.10 or newer**.
- `sudo ufw status`: if it says `active`, make sure `Nginx Full` (or 80 and 443) is listed as ALLOW.
  If only `Nginx HTTP` is allowed, run `sudo ufw allow 'Nginx Full'`.
- Note the file names in `sites-enabled` – those are the existing sites; do not edit them.

## Step 2 – Install the tools (does not touch existing sites)

```bash
sudo apt update
sudo apt install -y python3-venv python3-pip git certbot python3-certbot-nginx
```

(Only `apt install`; do **not** run `apt upgrade` now – do system upgrades at a separate, quiet time.)

## Step 3 – Download the website code

```bash
sudo mkdir -p /srv/sdrecruitment
sudo chown sdadmin:sdadmin /srv/sdrecruitment
git clone https://github.com/t-hinley/sd-recruitment.git /srv/sdrecruitment
cd /srv/sdrecruitment
```


## Step 4 – Python environment and packages

```bash
cd /srv/sdrecruitment
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt
```

## Step 5 – Settings file (`.env`)

```bash
cp .env.example .env
chmod 600 .env
.venv/bin/python -c "import secrets; print(secrets.token_urlsafe(50))"
nano .env
```

Copy the long random text from the third command. In `nano`, set these lines (use the arrow keys;
save with **Ctrl+O, Enter**, exit with **Ctrl+X**):

```
DJANGO_SECRET_KEY=<the long random text>
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=recruitment.example.com.au,www.recruitment.example.com.au
DJANGO_CSRF_TRUSTED_ORIGINS=https://recruitment.example.com.au,https://www.recruitment.example.com.au
SITE_URL=https://recruitment.example.com.au
DJANGO_BEHIND_PROXY=True
```

**Contact details** shown on the site (anything left empty is hidden):

```
BUSINESS_PHONE=04xx xxx xxx
BUSINESS_EMAIL=info@your-domain.com.au
BUSINESS_ADDRESS=Suite x, Street, Suburb WA 6000
```

**Email** (enquiry notifications). Use the SMTP details of the mailbox that should send them:

| Mailbox hosted at | EMAIL_HOST | EMAIL_PORT |
|---|---|---|
| Microsoft 365 / GoDaddy Microsoft email | `smtp.office365.com` | `587` |
| Google Workspace (use an App Password) | `smtp.gmail.com` | `587` |
| Other provider | from the provider's "SMTP settings" page | usually `587` |

Example for a Google Workspace mailbox (App Password from
<https://myaccount.google.com/apppasswords>, 2-Step Verification must be on):

```
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=info@your-domain.com.au
EMAIL_HOST_PASSWORD=<16-character App Password, no spaces>
DEFAULT_FROM_EMAIL=SD Recruitment Website <info@your-domain.com.au>
ENQUIRY_NOTIFICATION_EMAILS=info@your-domain.com.au
```

Notification emails never include the CV itself; staff download CVs from the admin.

## Step 6 – Database, styles, admin account

```bash
cd /srv/sdrecruitment
.venv/bin/python manage.py migrate
.venv/bin/python manage.py collectstatic --noinput
.venv/bin/python manage.py createsuperuser
.venv/bin/python manage.py check --deploy
```

`check --deploy` may warn about `SECURE_HSTS_SECONDS` – that is fine.

## Step 7 – Run the app as a service (starts automatically after reboots)

```bash
sudo cp /srv/sdrecruitment/deploy/sdrecruitment.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now sdrecruitment
systemctl status sdrecruitment --no-pager
```

It should say **active (running)**. If not: `sudo journalctl -u sdrecruitment -n 50 --no-pager`.

## Step 8 – Add the site to Nginx

```bash
sudo cp /srv/sdrecruitment/deploy/nginx-sdrecruitment.conf /etc/nginx/sites-available/sdrecruitment
sudo ln -s /etc/nginx/sites-available/sdrecruitment /etc/nginx/sites-enabled/sdrecruitment
sudo nginx -t
```

**Only if** `nginx -t` says `syntax is ok` and `test is successful`:

```bash
sudo systemctl reload nginx
```

If `nginx -t` shows an error, do **not** reload; remove the link with
`sudo rm /etc/nginx/sites-enabled/sdrecruitment` and send the error message for help.
(`reload` keeps SD Travels running; never use `restart` or `stop` for this.)

Now `http://recruitment.example.com.au` redirects to https, which will work after Step 9.

## Step 9 – Free SSL certificate (https)

```bash
sudo certbot --nginx -d recruitment.example.com.au -d www.recruitment.example.com.au
```

- Enter an email for renewal notices and agree to the terms.
- If asked about redirecting, choose **Redirect**.
- Certbot only edits the SD Recruitment Nginx file and renews automatically.

Open **https://recruitment.example.com.au** and **https://recruitment.example.com.au/admin/** – the site and admin
login should load with a padlock. Also open the SD Travels site to confirm it is unchanged.

## Step 10 – Resumes folder and backups

Uploaded CVs are saved in `/srv/sdrecruitment/private_media/resumes/` with random file names. Nginx
does not serve this folder, so CVs can only be opened by signed-in staff in the admin.

Back up the database **and** the CVs together, e.g. weekly:

```bash
tar czf ~/sdrecruitment-backup-$(date +%F).tar.gz -C /srv/sdrecruitment db.sqlite3 private_media
```

## Step 11 – Final checks

- [ ] https://recruitment.example.com.au opens with a padlock on desktop and phone.
- [ ] `https://www.recruitment.example.com.au` also opens with a padlock.
- [ ] Submit a vacancy, register a candidate **with a PDF CV**, and send a contact message →
      "Thank you" → notification emails arrive.
- [ ] In the admin, open the candidate and click **Download CV**.
- [ ] Add a test job under **Current opportunities** → it appears on the Candidates page → untick
      "Show on website" and it disappears.
- [ ] SD Travels and SD Commercial still work normally.
- [ ] Delete the test records afterwards (deleting a candidate also deletes their CV).

---

## Updating the site later

```bash
bash /srv/sdrecruitment/deploy/update.sh
```

It downloads the latest code, installs packages, updates the database and styles, and restarts the
app. Take a snapshot first for bigger updates.

## Adding another domain name later (e.g. `newdomain.com.au`)

1. DNS for the new domain: `A` record `@` → server IP, `CNAME` `www` → `@`.
2. `sudo nano /etc/nginx/sites-available/sdrecruitment` → on the `server_name` line add
   `newdomain.com.au www.newdomain.com.au` → `sudo nginx -t` → `sudo systemctl reload nginx`.
3. `sudo certbot --nginx -d recruitment.example.com.au -d www.recruitment.example.com.au -d newdomain.com.au -d www.newdomain.com.au`
4. `.env`: add the new names to `DJANGO_ALLOWED_HOSTS` and their `https://` versions to
   `DJANGO_CSRF_TRUSTED_ORIGINS`; set `SITE_URL` to the main address.
5. `sudo systemctl restart sdrecruitment`

## Useful commands

| Task | Command |
|---|---|
| Is the site running? | `systemctl status sdrecruitment --no-pager` |
| Restart the site | `sudo systemctl restart sdrecruitment` |
| App errors (last 50 lines) | `sudo journalctl -u sdrecruitment -n 50 --no-pager` |
| Nginx errors for this site | `sudo tail -n 50 /var/log/nginx/sdrecruitment.error.log` |
| Test Nginx config | `sudo nginx -t` |
| Back up enquiries and CVs | `tar czf ~/sdrecruitment-backup-$(date +%F).tar.gz -C /srv/sdrecruitment db.sqlite3 private_media` |

## Troubleshooting

| Problem | Fix |
|---|---|
| **502 Bad Gateway** | The app is not running: check `systemctl status sdrecruitment` and the journal command above. |
| **Bad Request (400)** | The name is missing from `DJANGO_ALLOWED_HOSTS` in `.env`; fix and restart. |
| **CSRF error on forms/admin** | `DJANGO_CSRF_TRUSTED_ORIGINS` must contain `https://recruitment.example.com.au`; restart. |
| Pages without styling | `cd /srv/sdrecruitment && .venv/bin/python manage.py collectstatic --noinput` |
| **413 Request Entity Too Large** on the candidate form | The CV is bigger than Nginx allows: check `client_max_body_size` in the Nginx file. |
| Certbot fails | DNS must point to this server and port 80 must be open (`sudo ufw status`). |
| No emails | Check `EMAIL_` settings; GoDaddy may block port 25, so use 587 (or 465 with `EMAIL_USE_SSL=True`, `EMAIL_USE_TLS=False`). |
| Undo everything | `sudo rm /etc/nginx/sites-enabled/sdrecruitment && sudo systemctl reload nginx && sudo systemctl disable --now sdrecruitment` – or restore the snapshot. |
