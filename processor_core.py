import csv
import os
import re
import time
from decimal import Decimal
from pathlib import Path
from typing import Optional

from dotenv import dotenv_values
from utils_llm import classify_command, extract_payment
from utils_chain import (
    User, get_eth_balance, get_usdc_balance, ensure_eth_topup_internal,
    erc20_transfer, MIN_AMOUNT, FEE, PAYMASTER_ETH_ADDR
)
from email.utils import parseaddr
from utils_email import send_email

CFG = dotenv_values('config.env')
DB_PATH = Path('database.csv')
QUEUE = Path('2process')
PAID = Path('paid')
ERROR = Path('error')
for d in [PAID, ERROR]: d.mkdir(exist_ok=True)

ETHERSCAN_TX = 'https://sepolia.etherscan.io/tx/'

HEADER_MANUAL = (
    "\n---------------------------------------------\n"
    "How to use SurePay (Sepolia / USDC)\n"
    "1) From your Gmail, email your request to the Paymaster address.\n"
    "2) Payment example: 'Send 10 USDC to bob@gmail.com' or 'pay 3.2 USDC to 0x...'.\n"
    "3) Fee: 0.10 USDC deducted from the receiver. Minimum: 0.11 USDC.\n"
    "4) External 0x recipients receive tokens; no ETH top-up and no email sent to them.\n"
    "5) Commands: Subject 'signup' (create wallet), 'balance' (get balances).\n"
    "6) Network: Ethereum Sepolia (testnet).\n"
)


def load_db() -> dict:
    users = {}
    if DB_PATH.exists():
        with DB_PATH.open('r', newline='', encoding='utf-8') as f:
            for row in csv.DictReader(f, fieldnames=['email','address','priv']):
                users[row['email'].strip().lower()] = User(row['email'], row['address'], row['priv'])
    return users


def save_user(u: User):
    exists = DB_PATH.exists()
    with DB_PATH.open('a', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        if not exists:
            # no header to keep it simple; already using fixed fieldnames
            pass
        w.writerow([u.email, u.address, u.priv])


def create_user(email_addr: str) -> User:
    from eth_account import Account
    acct = Account.create()
    u = User(email_addr.lower(), acct.address, acct.key.hex())
    save_user(u)
    return u


def find_or_create_recipient(recipient: str, users: dict) -> Optional[User]:
    # recipient is email -> internal user
    r = recipient.strip().lower()
    if '@' in r:
        return users.get(r) or create_user(r)
    return None


def handle_signup(sender: str):
    users = load_db()
    u = users.get(sender)
    if not u:
        u = create_user(sender)
    body = (
        f"Welcome! Your wallet is ready on Sepolia.\n"
        f"Address: {u.address}\n\n"
        "You can now receive USDC to your email.\n"
        "First-time send: fund this address with USDC (Sepolia) to start.\n"
        + HEADER_MANUAL
    )
    send_email(sender, 'Signup successful – Your Sepolia wallet', body)


def handle_balance(sender: str):
    users = load_db()
    u = users.get(sender)
    if not u:
        send_email(sender, 'Balance unavailable', 'You are not registered. Please send subject: signup')
        return
    eth = get_eth_balance(u.address)
    usdc = get_usdc_balance(u.address)
    body = (f"Balances for {u.address}:\nETH: {eth} wei\nUSDC: {usdc} \n" + HEADER_MANUAL)
    send_email(sender, 'Your balances', body)


def send_error(sender: str, subject: str, reason: str):
    send_email(sender, f'Payment failed – {reason}', f"We could not process your request: {reason}\n" + HEADER_MANUAL)


def process_payment(sender: str, subject: str, body: str):
    users = load_db()
    s = users.get(sender)
    if not s:
        send_error(sender, subject, 'unregistered sender (send subject: signup)')
        return

    # LLM extraction
    recipient, amount, err = extract_payment(body)
    if err or not recipient or amount is None:
        send_error(sender, subject, 'could not parse recipient/amount')
        return

    amt_dec = Decimal(str(amount))
    if amt_dec < MIN_AMOUNT:
        send_error(sender, subject, f'minimum amount is {MIN_AMOUNT} USDC')
        return

    # Resolve recipient
    recipient_user = None
    is_external_address = False
    if '@' in recipient:
        users = load_db()  # reload in case signup just happened
        recipient_user = find_or_create_recipient(recipient, users)
        to_addr = recipient_user.address
    else:
        # expect 0x...
        if not recipient.lower().startswith('0x') or len(recipient) != 42:
            send_error(sender, subject, 'invalid recipient address')
            return
        to_addr = recipient
        is_external_address = True

    # Check sender balance
    sender_usdc = get_usdc_balance(s.address)
    if sender_usdc < amt_dec:
        send_error(sender, subject, f'insufficient USDC (have {sender_usdc}, need {amt_dec})')
        return

    # Top-up ETH for sender and internal recipient if needed
    try:
        ensure_eth_topup_internal(s.address)
        if not is_external_address and recipient_user:
            ensure_eth_topup_internal(recipient_user.address)
    except Exception as e:
        send_error(sender, subject, f'eth top-up failed: {e}')
        return

    # Execute two transfers from sender: net and fee
    net = (amt_dec - FEE)
    if net <= Decimal('0'):
        send_error(sender, subject, 'amount must be > fee (0.10)')
        return

    try:
        tx1 = erc20_transfer(s.address, s.priv, to_addr, net)
        tx2 = erc20_transfer(s.address, s.priv, PAYMASTER_ETH_ADDR, FEE)
    except Exception as e:
        send_error(sender, subject, f'blockchain error: {e}')
        return

    # Success notifications
    # Sender email (no fee mention)
    sender_body = (
        f"Your payment request succeeded.\n\n"
        f"Sent: {amt_dec} USDC to {recipient}.\n"
        f"Tx (to recipient): {ETHERSCAN_TX}{tx1}\n"
        f"Tx (fee): {ETHERSCAN_TX}{tx2}\n"
        + HEADER_MANUAL
    )
    send_email(sender, f'Payment completed – {amt_dec} USDC', sender_body)

    # Recipient email (only if internal email recipient)
    if not is_external_address and recipient_user:
        recipient_body = (
            f"You received {amt_dec} USDC from {sender}.\n"
            f"Service fee: 0.10 USDC deducted. Net received: {net} USDC.\n"
            f"Tx: {ETHERSCAN_TX}{tx1}\n"
            + HEADER_MANUAL
        )
        send_email(recipient_user.email, f'You received {amt_dec} USDC', recipient_body)


def main_loop():
    print('[processor] watching 2process/...')
    while True:
        for f in sorted(QUEUE.glob('*.txt')):
            try:
                line = f.read_text(encoding='utf-8')
                # format: "sender","subject","body"
                parts = []
                cur = ''
                inq = False
                for ch in line:
                    if ch == '"':
                        inq = not inq
                        continue
                    if ch == ',' and not inq:
                        parts.append(cur)
                        cur = ''
                    else:
                        cur += ch
                if cur:
                    parts.append(cur)
                parts = [p.strip() for p in parts]
                sender = parts[0]
                subject = parts[1]
                body = parts[2]
                sender_addr = parseaddr(sender)[1].lower()

                cmd = classify_command(subject, body)
                if cmd == 'signup':
                    handle_signup(sender_addr)
                elif cmd == 'balance':
                    handle_balance(sender_addr)
                else:
                    process_payment(sender_addr, subject, body)

                f.unlink()
            except Exception as e:
                (ERROR / (f.name + '.err.txt')).write_text(str(e), encoding='utf-8')
                try:
                    f.unlink()
                except:
                    pass
        time.sleep(1)

if __name__ == '__main__':
    main_loop()