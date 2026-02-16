import json
import os
import sys
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import urljoin
import smtplib
from email.message import EmailMessage

# 1. Scrape les propositions de l'ADUM

url = "https://adum.fr/as/ed/propositionFR.pl?site=adumR"
STATE_FILE = "adum_state.json"

resp = requests.get(
    url,
    headers={"User-Agent": "Mozilla/5.0 (watch-url/1.0)"},
    timeout=30,
)
resp.raise_for_status()

soup = BeautifulSoup(resp.text, "lxml")
markers = soup.find_all("span", string=lambda s: s and "☛" in s)

items = []
for m in markers:
    a = m.find_next_sibling("a")
    if not a:
        continue

    title = a.get_text(strip=True)
    href = a.get("href")
    if not href:
        continue

    full_url = urljoin(url, href)  # rend l'URL absolue
    items.append({"title": title, "url": full_url})

# dédoublonner au cas où
seen = set()
unique_items = []
for it in items:
    key = it["url"]
    if key not in seen:
        seen.add(key)
        unique_items.append(it)

items = unique_items
print("Nb propositions:", len(items))

# 2. Comparer avec l'état précédent et afficher les changements


def load_state(path: str) -> dict:
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        return {"items": [], "updated_at": None}
    with open(path, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return {"items": [], "updated_at": None}


def save_state(path: str, items: list[dict]) -> None:
    state = {
        "updated_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "items": items,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def send_email(subject: str, body: str) -> None:
    """
    Envoie un mail via SMTP.
    Variables d'env attendues:
      SMTP_HOST, SMTP_PORT (optionnel, défaut 587), SMTP_USER, SMTP_PASS, MAIL_TO, MAIL_FROM (optionnel)
    """
    smtp_host = os.environ["SMTP_HOST"]
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    smtp_user = os.environ["SMTP_USER"]
    smtp_pass = os.environ["SMTP_PASS"]

    mail_from = os.environ.get("MAIL_FROM", smtp_user)
    mail_to = os.environ["MAIL_TO"]  # "a@x.com" ou "a@x.com,b@y.com"

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = mail_from
    msg["To"] = mail_to
    msg.set_content(body)

    with smtplib.SMTP(smtp_host, smtp_port) as s:
        s.starttls()
        s.login(smtp_user, smtp_pass)
        s.send_message(msg)


old_state = load_state(STATE_FILE)
old_items = old_state.get("items", [])

old_urls = {it["url"] for it in old_items}
new_urls = {it["url"] for it in items}

added_urls = new_urls - old_urls
removed_urls = old_urls - new_urls

added = [it for it in items if it["url"] in added_urls]
removed = [it for it in old_items if it["url"] in removed_urls]

print("\n--- AJOUTS ---")
for it in added:
    print(f"- {it['title']} | {it['url']}")

print("\n--- SUPPRESSIONS ---")
for it in removed:
    print(f"- {it['title']} | {it['url']}")

# 3. Envoyer un mail tous les matins, même s'il n'y a pas d'ajout

now = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")

lines = []
lines.append(f"Rapport quotidien ADUM")
lines.append(f"Date: {now}")
lines.append(f"Page: {url}")
lines.append("")
lines.append(f"Nombre de propositions actuelles: {len(items)}")
lines.append("")

lines.append(f"AJOUTS ({len(added)})")
if added:
    for it in added:
        lines.append(f"- {it['title']}")
        lines.append(f"  {it['url']}")
else:
    lines.append("- Aucun ajout")

lines.append("")
lines.append(f"SUPPRESSIONS ({len(removed)})")
if removed:
    for it in removed:
        lines.append(f"- {it['title']}")
        lines.append(f"  {it['url']}")
else:
    lines.append("- Aucune suppression")

body = "\n".join(lines)
subject = f"[ADUM] Rapport quotidien ({len(added)} ajout(s), {len(removed)} suppression(s))"

# Envoi systématique (même sans ajout/suppression)
send_email(subject, body)

# 4. Toujours sauvegarder l'état du jour (même si pas de changement)
save_state(STATE_FILE, items)