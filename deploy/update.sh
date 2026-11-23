#!/usr/bin/env bash
# Update the SD Recruitment website to the latest code on GitHub.
# Run on the server:  bash /srv/sdrecruitment/deploy/update.sh
set -euo pipefail
cd /srv/sdrecruitment
echo "== Getting the latest code"
git pull --ff-only
echo "== Installing packages"
.venv/bin/pip install -q -r requirements.txt
echo "== Updating the database"
.venv/bin/python manage.py migrate --noinput
echo "== Updating styles and scripts"
.venv/bin/python manage.py collectstatic --noinput -v0
echo "== Checking settings"
.venv/bin/python manage.py check --deploy --fail-level ERROR
echo "== Restarting the website"
sudo systemctl restart sdrecruitment
sleep 2
systemctl is-active --quiet sdrecruitment && echo "Done: website is running." || { echo "Website did not start:"; sudo journalctl -u sdrecruitment -n 30 --no-pager; exit 1; }
