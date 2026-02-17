import json
import os
import sys
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import urljoin
import smtplib
from email.message import EmailMessage
from html import escape

from dotenv import load_dotenv
load_dotenv()

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


def send_email(subject: str, text_body: str, html_body: str) -> None:
    """
    Envoie un mail via SMTP (texte + HTML).
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

    # Fallback texte
    msg.set_content(text_body)
    # Version HTML (jolie + liens cliquables)
    msg.add_alternative(html_body, subtype="html")

    with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as s:
        s.ehlo()
        s.starttls()
        s.ehlo()
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

# 3. Construire un mail (texte + HTML) et l'envoyer même s'il n'y a pas d'ajout

now = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
subject = f"[ADUM] Rapport quotidien ({len(added)} ajout(s), {len(removed)} suppression(s))"

# ---------
# Corps TEXTE (fallback)
# ---------
lines_txt = []
lines_txt.append("Rapport quotidien ADUM")
lines_txt.append(f"Date: {now}")
lines_txt.append(f"Page: {url}")
lines_txt.append("")
lines_txt.append(f"Nombre de propositions actuelles: {len(items)}")
lines_txt.append("")

lines_txt.append(f"AJOUTS ({len(added)})")
if added:
    for it in added:
        lines_txt.append(f"- {it['title']} : {it['url']}")
else:
    lines_txt.append("- Aucun ajout")

lines_txt.append("")
lines_txt.append(f"SUPPRESSIONS ({len(removed)})")
if removed:
    for it in removed:
        lines_txt.append(f"- {it['title']} : {it['url']}")
else:
    lines_txt.append("- Aucune suppression")

text_body = "\n".join(lines_txt)

# ---------
# Corps HTML (liens cliquables + mise en forme simple)
# ---------

def render_list_html(items_list, empty_text: str) -> str:
    if not items_list:
        return f'<p style="margin:0;color:#555;">{escape(empty_text)}</p>'

    li = []
    for it in items_list:
        title = escape(it["title"])
        link = escape(it["url"])

        li.append(
            f'<li style="margin:10px 0;">'
            f'<a href="{link}" '
            f'style="color:#1a73e8;text-decoration:none;font-weight:600;">'
            f'{title}'
            f'</a>'
            f'</li>'
        )

    return '<ul style="padding-left:18px;margin:8px 0;">' + "".join(li) + "</ul>"

html_body = f"""\
<!doctype html>
<html>
  <body style="font-family:Arial,Helvetica,sans-serif;background:#f6f7fb;padding:18px;">
    <div style="max-width:720px;margin:0 auto;background:#ffffff;border:1px solid #e6e8ef;border-radius:12px;overflow:hidden;">
      <div style="padding:16px 18px;background:#0b57d0;color:#fff;">
        <div style="font-size:18px;font-weight:700;">Rapport quotidien ADUM</div>
        <div style="font-size:12px;opacity:0.9;margin-top:4px;">{escape(now)}</div>
      </div>

      <div style="padding:18px;">
        <p style="margin:0 0 10px 0;">
          Page surveillée :
          <a href="{escape(url)}" style="color:#1a73e8;text-decoration:none;">{escape(url)}</a>
        </p>

        <div style="display:flex;gap:10px;flex-wrap:wrap;margin:12px 0 18px 0;">
          <div style="padding:10px 12px;border:1px solid #e6e8ef;border-radius:10px;">
            <div style="font-size:12px;color:#666;">Propositions actuelles</div>
            <div style="font-size:20px;font-weight:700;">{len(items)}</div>
          </div>
          <div style="padding:10px 12px;border:1px solid #e6e8ef;border-radius:10px;">
            <div style="font-size:12px;color:#666;">Ajouts</div>
            <div style="font-size:20px;font-weight:700;">{len(added)}</div>
          </div>
          <div style="padding:10px 12px;border:1px solid #e6e8ef;border-radius:10px;">
            <div style="font-size:12px;color:#666;">Suppressions</div>
            <div style="font-size:20px;font-weight:700;">{len(removed)}</div>
          </div>
        </div>

        <h3 style="margin:18px 0 8px 0;">AJOUTS ({len(added)})</h3>
        {render_list_html(added, "Aucun ajout")}

        <h3 style="margin:18px 0 8px 0;">SUPPRESSIONS ({len(removed)})</h3>
        {render_list_html(removed, "Aucune suppression")}

        <hr style="border:none;border-top:1px solid #e6e8ef;margin:18px 0;" />
        <div style="font-size:12px;color:#666;">
          Mail généré automatiquement par un script local.
        </div>
      </div>
    </div>
  </body>
</html>
"""

# Debug env (optionnel)
required = ["SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASS", "MAIL_TO"]
missing = [k for k in required if not os.getenv(k)]
print("Missing env:", missing)
print("SMTP_HOST:", os.getenv("SMTP_HOST"))
print("SMTP_PORT:", os.getenv("SMTP_PORT"))
print("SMTP_USER:", os.getenv("SMTP_USER"))
print("MAIL_TO:", os.getenv("MAIL_TO"))

# Envoi systématique (texte + HTML)
send_email(subject, text_body, html_body)

# 4. Toujours sauvegarder l'état du jour (même si pas de changement)
save_state(STATE_FILE, items)