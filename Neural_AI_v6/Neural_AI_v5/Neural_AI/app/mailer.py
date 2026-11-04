"""Sends verification emails through the Mailjet HTTPS API (stdlib only)."""
import base64
import json
import logging
import urllib.error
import urllib.request

from . import config

log = logging.getLogger("neural.mail")
API_URL = "https://api.mailjet.com/v3.1/send"


class MailError(Exception):
    pass


def configured() -> bool:
    return bool(config.MAILJET_API_KEY and config.MAILJET_SECRET_KEY and config.MAIL_FROM)


def send(to: str, subject: str, text: str, html: str) -> None:
    if not configured():
        raise MailError("Email sending is not configured.")
    payload = {"Messages": [{
        "From": {"Email": config.MAIL_FROM, "Name": config.MAIL_FROM_NAME},
        "To": [{"Email": to}],
        "Subject": subject,
        "TextPart": text,
        "HTMLPart": html,
    }]}
    auth = base64.b64encode(f"{config.MAILJET_API_KEY}:{config.MAILJET_SECRET_KEY}".encode()).decode()
    req = urllib.request.Request(API_URL, data=json.dumps(payload).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "Authorization": "Basic " + auth})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            body = json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        log.error("Mailjet HTTP %s: %s", e.code, e.read()[:300])
        raise MailError("Mail provider rejected the request.")
    except Exception as e:  # network errors, timeouts
        log.error("Mailjet request failed: %s", e)
        raise MailError("Could not reach the mail provider.")
    msgs = body.get("Messages") or [{}]
    if msgs[0].get("Status") != "success":
        log.error("Mailjet did not accept the message: %s", str(msgs[0])[:300])
        raise MailError("Mail provider did not accept the message.")


def send_code(to: str, code: str) -> None:
    minutes = config.CODE_TTL_SECONDS // 60
    text = (f"Your Neural AI verification code is {code}\n\n"
            f"It expires in {minutes} minutes. If you did not create an account, you can ignore this email.\n\n"
            "Please do not reply to this email.")
    html = ('<div style="font-family:Arial,sans-serif;max-width:420px;margin:auto;padding:24px">'
            '<h2 style="margin:0 0 12px">Neural AI</h2>'
            '<p>Your verification code is:</p>'
            f'<p style="font-size:32px;letter-spacing:6px;font-weight:700;margin:8px 0">{code}</p>'
            f'<p style="color:#555">It expires in {minutes} minutes. If you did not create an account, you can ignore this email.</p>'
            '<p style="color:#888;font-size:12px">Please do not reply to this email.</p></div>')
    send(to, "Your Neural AI verification code", text, html)
