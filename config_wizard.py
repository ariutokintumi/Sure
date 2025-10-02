import os
import sys
import getpass
from pathlib import Path
from dotenv import dotenv_values
from eth_account import Account

CONFIG_PATH = Path('config.env')

USDC_SEPOLIA = '0x1c7D4B196Cb0C7B01d743Fbc6116a902379C7238'  # 6 decimals
DEFAULT_IMAP_POLL_SECONDS = '5'

BANNER = r"""
========================================
 SurePay Config Wizard (Sepolia / USDC)
========================================
"""

FIELDS = [
    ('PAYMASTER_EMAIL', 'Paymaster Gmail address (must be @gmail.com): '),
    ('PAYMASTER_NAME',  'Paymaster display name (e.g., Paymaster Hackathon): '),
    ('PAYMASTER_APP_PASSWORD', 'Gmail App Password (recommended): ', True),
    ('ALCHEMY_HTTP_URL', 'Alchemy Sepolia HTTP URL (https://...): '),
]

LLM_CHOICES = {
    'openai': ['OPENAI_API_KEY'],
    'openrouter': ['OPENROUTER_API_KEY', 'OPENROUTER_BASE']
}

def ensure_dirs():
    for d in ['mails', '2process', 'paid', 'error', 'invalid']:
        Path(d).mkdir(parents=True, exist_ok=True)

def prompt_hidden(prompt: str) -> str:
    return getpass.getpass(prompt)

def prompt_visible(prompt: str) -> str:
    return input(prompt).strip()

def main():
    print(BANNER)
    ensure_dirs()

    if CONFIG_PATH.exists():
        print(f"Existing {CONFIG_PATH} found. Values will be updated/merged.\n")
        existing = dotenv_values(CONFIG_PATH)
    else:
        existing = {}

    out = dict(existing)

    # Core fields
    for key, question, *rest in FIELDS:
        hidden = bool(rest and rest[0])
        default = out.get(key, '')
        value = ''
        if default:
            print(f"Current {key} = {default}")
            use = input(f"Keep current {key}? [Y/n]: ").strip().lower() or 'y'
            if use.startswith('y'):
                value = default
        if not value:
            value = (prompt_hidden(question) if hidden else prompt_visible(question))
        out[key] = value

    # LLM selection
    print("\nChoose LLM provider:")
    print("  1) OpenAI")
    print("  2) OpenRouter")
    choice = input("Select [1/2]: ").strip()
    if choice == '1':
        out['LLM_PROVIDER'] = 'openai'
        if not out.get('OPENAI_API_KEY'):
            out['OPENAI_API_KEY'] = prompt_hidden('OpenAI API Key: ')
        # optional: model override
        out['OPENAI_MODEL'] = out.get('OPENAI_MODEL', 'gpt-4o-mini')
    else:
        out['LLM_PROVIDER'] = 'openrouter'
        if not out.get('OPENROUTER_API_KEY'):
            out['OPENROUTER_API_KEY'] = prompt_hidden('OpenRouter API Key: ')
        out['OPENROUTER_BASE'] = out.get('OPENROUTER_BASE', 'https://openrouter.ai/api/v1')
        out['OPENROUTER_MODEL'] = out.get('OPENROUTER_MODEL', 'openai/gpt-4o-mini')

    # Poll seconds
    poll = input(f"\nIMAP poll interval seconds [{DEFAULT_IMAP_POLL_SECONDS}]: ").strip()
    out['IMAP_POLL_SECONDS'] = poll or DEFAULT_IMAP_POLL_SECONDS

    # Fixed token/network
    out['USDC_CONTRACT'] = USDC_SEPOLIA
    out['CHAIN_ID'] = '11155111'

    # Generate Paymaster ETH account (only if absent)
    if not out.get('PAYMASTER_ETH_PRIV') or not out.get('PAYMASTER_ETH_ADDR'):
        acct = Account.create()
        out['PAYMASTER_ETH_PRIV'] = acct.key.hex()
        out['PAYMASTER_ETH_ADDR'] = acct.address
        print("\nGenerated Paymaster ETH account (Sepolia):")
        print(f"  Address: {acct.address}")
        print("Fund this with Sepolia ETH and USDC for testing.")

    # Write config.env
    lines = []
    for k, v in out.items():
        if '\n' in str(v):
            v = v.replace('\n', '\\n')
        lines.append(f"{k}={v}")
    CONFIG_PATH.write_text('\n'.join(lines) + '\n', encoding='utf-8')

    print(f"\nSaved {CONFIG_PATH}. Done.\n")

if __name__ == '__main__':
    main()