import time
from utils_email import imap_fetch_new, IMAP_POLL_SECONDS

if __name__ == '__main__':
    print(f"[checker_imap] polling every {IMAP_POLL_SECONDS}s ...")
    while True:
        try:
            imap_fetch_new()
        except Exception as e:
            print(f"[checker_imap] error: {e}")
        time.sleep(IMAP_POLL_SECONDS)