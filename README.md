# SurePay Email USDC (Sepolia)
Email-driven USDC payments on Ethereum Sepolia using Gmail + AI (OpenAI or OpenRouter) + Web3.py.

## Features
- Gmail IMAP polling (INBOX + Spam), deletes after ingest to avoid duplicates
- Header authenticity check (Authentication-Results: spf=pass & dkim=pass for gmail.com; top Received from google)
- AI-only natural language parsing of: recipient (email or 0x-address) and amount (USDC)
- Commands: `signup` (subject), `balance`
- Sender must exist to send/balance (signup creates). Recipient (email) auto-created; external 0x-address allowed (no ETH top-up; no recipient email)
- Min transfer: 0.11 USDC (flat fee 0.10 paid by receiver)
- ETH top-up 0.0001 for internal sender/recipient if low
- Strict nonce handling; wait 10s between any transfers; wait for receipts; include Etherscan links
- Success & error notifications by email (from Paymaster)

## Quickstart
1. `python -m venv .venv && source .venv/bin/activate` (or Windows equivalent)
2. `pip install -r requirements.txt`
3. Run the wizard: `python config_wizard.py`
&nbsp;  - Paste: Paymaster Gmail + App Password, Alchemy Sepolia HTTP URL, choose LLM provider + key, IMAP poll seconds
&nbsp;  - Wizard **generates Paymaster ETH account** → fund it with Sepolia ETH and (optionally) Sepolia USDC
4. Launch services (separate terminals or tmux):
&nbsp;  - `python checker_imap.py`
&nbsp;  - `python interpreter_headers.py`
&nbsp;  - `python processor_core.py`
&nbsp;  - `python mailer_notify.py`
5. Compose emails from any **@gmail.com** to the paymaster:
&nbsp;  - Payment: "Send 12.5 USDC to alice@gmail.com" or "pay 3.2 USDC to 0x..."
&nbsp;  - Signup: Subject `signup` (empty body OK)
&nbsp;  - Balance: Subject `balance` or include the word `balance` in body

## Notes
- Token: USDC on Sepolia (6 decimals) at `0x1c7D4B196Cb0C7B01d743Fbc6116a902379C7238`
- Chain ID: 11155111
- Folders are created automatically on first run
- This is a hackathon demo; keep `config.env` & `database.csv` private
