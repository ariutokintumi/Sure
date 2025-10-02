import re
from pathlib import Path
from utils_email import parse_headers_from_bytes

MAILS = Path('mails')
TWO_PROCESS = Path('2process')
INVALID = Path('invalid')
TWO_PROCESS.mkdir(exist_ok=True)
INVALID.mkdir(exist_ok=True)

GMAIL_SENDER_RE = re.compile(r"@gmail\.com\s*>?$", re.IGNORECASE)


def is_authentic_gmail(msg) -> bool:
    # Check From domain
    from_raw = msg.get('From', '')
    if '@gmail.com' not in from_raw.lower():
        return False

    # Require Authentication-Results with spf=pass and dkim=pass for gmail.com
    auth = msg.get_all('Authentication-Results', [])
    auth_str = '\n'.join(auth)
    if 'spf=pass' not in auth_str.lower():
        return False
    if 'dkim=pass' not in auth_str.lower():
        return False
    if 'gmail.com' not in auth_str.lower():
        return False

    # Top Received should mention google
    recvd_all = msg.get_all('Received', [])
    if not recvd_all:
        return False
    top = recvd_all[0].lower()
    if '.google.com' not in top and 'google.com' not in top:
        return False
    return True


def extract_sender(msg) -> str:
    from email.utils import parseaddr
    name, addr = parseaddr(msg.get('From', ''))
    return addr.strip()


def extract_subject_body(msg):
    subject = msg.get('Subject', '')
    body = ''
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            if ctype == 'text/plain':
                body += part.get_payload(decode=True).decode(errors='ignore')
    else:
        body = msg.get_payload(decode=True).decode(errors='ignore')
    return subject, body

if __name__ == '__main__':
    for eml in sorted(MAILS.glob('*.eml')):
        raw = eml.read_bytes()
        msg = parse_headers_from_bytes(raw)
        if not is_authentic_gmail(msg):
            eml.rename(INVALID / eml.name)
            continue
        sender = extract_sender(msg)
        subject, body = extract_subject_body(msg)
        # Save one-line CSV-like row for processor
        line = f'"{sender}","{subject}","{body.replace("\n", " ").replace("\r", " ")}"\n'
        out = TWO_PROCESS / (eml.stem + '.txt')
        out.write_text(line, encoding='utf-8')
        eml.unlink()