import email
import imaplib
import os
import smtplib
import ssl
from email.mime.text import MIMEText
from email.utils import formataddr
from pathlib import Path
from dotenv import dotenv_values

CFG = dotenv_values('config.env')
MAILS = Path('mails')
INVALID = Path('invalid')
MAILS.mkdir(exist_ok=True)
INVALID.mkdir(exist_ok=True)

IMAP_SERVER = 'imap.gmail.com'
SMTP_SERVER = 'smtp.gmail.com'
SMTP_PORT_SSL = 465

PAYMASTER_EMAIL = CFG.get('PAYMASTER_EMAIL', '')
PAYMASTER_NAME = CFG.get('PAYMASTER_NAME', 'Paymaster')
PAYMASTER_APP_PASSWORD = CFG.get('PAYMASTER_APP_PASSWORD', '')
IMAP_POLL_SECONDS = int(CFG.get('IMAP_POLL_SECONDS', '5'))


def save_and_delete_imap_message(conn, msg_id: bytes, folder: str = 'INBOX'):
    typ, data = conn.fetch(msg_id, '(RFC822)')
    if typ != 'OK':
        return False
    raw = data[0][1]
    # save to file
    fn = MAILS / f"{msg_id.decode()}_{folder}.eml"
    fn.write_bytes(raw)
    # mark deleted and expunge
    conn.store(msg_id, '+FLAGS', r'(\Deleted)')
    return True


def imap_login():
    m = imaplib.IMAP4_SSL(IMAP_SERVER)
    m.login(PAYMASTER_EMAIL, PAYMASTER_APP_PASSWORD)
    return m


def imap_fetch_new():
    """Fetches new (UNSEEN) from INBOX and Spam, saves, and deletes from server."""
    conn = imap_login()
    try:
        for folder in ['INBOX', '[Gmail]/Spam']:
            try:
                conn.select(folder)
                typ, ids = conn.search(None, 'UNSEEN')
                if typ != 'OK':
                    continue
                for msg_id in ids[0].split():
                    if save_and_delete_imap_message(conn, msg_id, folder=folder):
                        pass
                conn.expunge()
            except imaplib.IMAP4.error:
                continue
    finally:
        conn.logout()


def parse_headers_from_bytes(raw_bytes: bytes) -> email.message.Message:
    return email.message_from_bytes(raw_bytes)


def send_email(to_addr: str, subject: str, body: str):
    msg = MIMEText(body, 'plain', 'utf-8')
    msg['Subject'] = subject
    msg['From'] = formataddr((PAYMASTER_NAME, PAYMASTER_EMAIL))
    msg['To'] = to_addr

    context = ssl.create_default_context()
    with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT_SSL, context=context) as server:
        server.login(PAYMASTER_EMAIL, PAYMASTER_APP_PASSWORD)
        server.sendmail(PAYMASTER_EMAIL, [to_addr], msg.as_string())