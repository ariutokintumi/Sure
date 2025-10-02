import json
import os
from typing import Optional, Tuple
import requests
from dotenv import dotenv_values

CFG = dotenv_values('config.env')
LLM_PROVIDER = CFG.get('LLM_PROVIDER', 'openai')

OPENAI_API_KEY = CFG.get('OPENAI_API_KEY')
OPENAI_MODEL = CFG.get('OPENAI_MODEL', 'gpt-4o-mini')

OPENROUTER_API_KEY = CFG.get('OPENROUTER_API_KEY')
OPENROUTER_BASE = CFG.get('OPENROUTER_BASE', 'https://openrouter.ai/api/v1')
OPENROUTER_MODEL = CFG.get('OPENROUTER_MODEL', 'openai/gpt-4o-mini')

PAYMENT_PROMPT = (
    "You are an extractor. Return strict JSON with keys: recipient (string), amount (number). "
    "recipient is either an email (contains @) or a 0x... address. "
    "amount is USDC (decimal). If not clearly present, respond with: {\"error\":\"missing\"}.\n\n"
    "Text:\n"
)

CMD_PROMPT = (
    "You are a classifier. For the provided email subject and body, return one of: "
    "\"payment\", \"signup\", \"balance\". Output strict JSON {\"command\":<value>} only.\n"
)


def _openai_chat(messages):
    url = 'https://api.openai.com/v1/chat/completions'
    headers = {
        'Authorization': f'Bearer {OPENAI_API_KEY}',
        'Content-Type': 'application/json'
    }
    data = {
        'model': OPENAI_MODEL,
        'messages': messages,
        'temperature': 0.0
    }
    r = requests.post(url, headers=headers, json=data, timeout=30)
    r.raise_for_status()
    return r.json()['choices'][0]['message']['content']


def _openrouter_chat(messages):
    url = f'{OPENROUTER_BASE}/chat/completions'
    headers = {
        'Authorization': f'Bearer {OPENROUTER_API_KEY}',
        'Content-Type': 'application/json'
    }
    data = {
        'model': OPENROUTER_MODEL,
        'messages': messages,
        'temperature': 0.0
    }
    r = requests.post(url, headers=headers, json=data, timeout=30)
    r.raise_for_status()
    return r.json()['choices'][0]['message']['content']


def llm_chat(system: str, user: str) -> str:
    if LLM_PROVIDER == 'openai':
        return _openai_chat([
            {"role": "system", "content": system},
            {"role": "user", "content": user}
        ])
    else:
        return _openrouter_chat([
            {"role": "system", "content": system},
            {"role": "user", "content": user}
        ])


def classify_command(subject: str, body: str) -> str:
    content = json.loads(llm_chat(CMD_PROMPT, json.dumps({"subject": subject or "", "body": body or ""})))
    return content.get('command', 'payment')


def extract_payment(body: str) -> Tuple[Optional[str], Optional[float], Optional[str]]:
    """Returns (recipient, amount, error)."""
    try:
        raw = llm_chat(PAYMENT_PROMPT, body)
        data = json.loads(raw)
        if 'error' in data:
            return None, None, 'parse_failed'
        recipient = data.get('recipient')
        amount = data.get('amount')
        if recipient and isinstance(amount, (int, float)):
            return recipient.strip(), float(amount), None
        return None, None, 'parse_failed'
    except Exception as e:
        return None, None, f'parse_exception:{e}'