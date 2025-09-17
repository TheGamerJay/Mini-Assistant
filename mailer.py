import os, smtplib, ssl, json, logging, socket
from email.message import EmailMessage
import requests

class Mailer:
    def __init__(self, resend_api_key=None, resend_from=None,
                 smtp_host=None, smtp_port=587, smtp_user=None, smtp_pass=None,
                 smtp_from=None, use_tls=True, dev_echo=False):
        self.resend_api_key = resend_api_key
        self.resend_from = resend_from
        self.smtp = dict(host=smtp_host, port=smtp_port, user=smtp_user, pw=smtp_pass,
                         sender=smtp_from or resend_from, tls=use_tls)
        self.dev_echo = dev_echo
        self.backend = self._choose_backend()

    def _choose_backend(self):
        if self.dev_echo: return "echo"
        if self.resend_api_key and self.resend_from: return "resend"
        if self.smtp["host"] and self.smtp["sender"]: return "smtp"
        return "disabled"

    def send(self, to, subject, text, html=None):
        if self.backend == "disabled":
            logging.warning("Email disabled; would send to %s: %s", to, subject); return
        if self.backend == "echo":
            print(f"[MAIL ECHO] to={to} subject={subject}\n{text}\n"); return
        if self.backend == "resend":
            try:
                r = requests.post(
                    "https://api.resend.com/emails",
                    headers={"Authorization": f"Bearer {self.resend_api_key}",
                             "Content-Type": "application/json"},
                    data=json.dumps({"from": self.resend_from, "to": [to], "subject": subject,
                                     "html": html or f"<pre>{text}</pre>", "text": text})
                )
                r.raise_for_status()
            except Exception as e:
                logging.exception("Resend send failed: %s", e)
            return
        if self.backend == "smtp":
            msg = EmailMessage()
            msg["From"] = self.smtp["sender"]
            msg["To"] = to
            msg["Subject"] = subject
            msg.set_content(text)
            if html:
                msg.add_alternative(html, subtype="html")
            context = ssl.create_default_context()
            try:
                with smtplib.SMTP(self.smtp["host"], self.smtp["port"], timeout=15) as s:
                    if self.smtp["tls"]: s.starttls(context=context)
                    if self.smtp["user"] and self.smtp["pw"]:
                        s.login(self.smtp["user"], self.smtp["pw"])
                    s.send_message(msg)
            except (smtplib.SMTPException, socket.error) as e:
                logging.exception("SMTP send failed: %s", e)

    def describe(self):
        return {
            "MAIL_BACKEND": self.backend,
            "smtp_host_set": bool(self.smtp["host"]),
            "smtp_port": self.smtp["port"],
            "use_tls": bool(self.smtp["tls"]),
            "default_sender": self.smtp["sender"] or self.resend_from,
        }