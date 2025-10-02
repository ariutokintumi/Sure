import time
from dataclasses import dataclass
from decimal import Decimal, ROUND_DOWN
from pathlib import Path
from typing import Optional, Tuple

from dotenv import dotenv_values
from web3 import Web3
from web3.middleware import geth_poa_middleware
from eth_account import Account

CFG = dotenv_values('config.env')
ALCHEMY_HTTP_URL = CFG.get('ALCHEMY_HTTP_URL')
CHAIN_ID = int(CFG.get('CHAIN_ID', '11155111'))
USDC_CONTRACT = CFG.get('USDC_CONTRACT')
PAYMASTER_ETH_PRIV = CFG.get('PAYMASTER_ETH_PRIV')
PAYMASTER_ETH_ADDR = CFG.get('PAYMASTER_ETH_ADDR')

# Minimal ERC20 ABI subset
ERC20_ABI = [
    {"name":"transfer","type":"function","stateMutability":"nonpayable",
     "inputs":[{"name":"_to","type":"address"},{"name":"_value","type":"uint256"}],"outputs":[{"name":"","type":"bool"}]},
    {"name":"balanceOf","type":"function","stateMutability":"view",
     "inputs":[{"name":"owner","type":"address"}],"outputs":[{"name":"","type":"uint256"}]},
    {"name":"decimals","type":"function","stateMutability":"view","inputs":[],"outputs":[{"name":"","type":"uint8"}]}
]

w3 = Web3(Web3.HTTPProvider(ALCHEMY_HTTP_URL, request_kwargs={"timeout": 60}))
w3.middleware_onion.inject(geth_poa_middleware, layer=0)

USDC = w3.eth.contract(address=Web3.to_checksum_address(USDC_CONTRACT), abi=ERC20_ABI)

MIN_AMOUNT = Decimal('0.11')
FEE = Decimal('0.10')
TOPUP_WEI = w3.to_wei(Decimal('0.0001'), 'ether')

@dataclass
class User:
    email: str
    address: str
    priv: str


def to_wei_usdc(amount_dec: Decimal) -> int:
    # 6 decimals
    scaled = (amount_dec * Decimal(10**6)).quantize(Decimal(1), rounding=ROUND_DOWN)
    return int(scaled)


def from_wei_usdc(amount_int: int) -> Decimal:
    return (Decimal(amount_int) / Decimal(10**6)).quantize(Decimal('0.000001'))


def get_eth_balance(addr: str) -> int:
    return w3.eth.get_balance(Web3.to_checksum_address(addr))


def get_usdc_balance(addr: str) -> Decimal:
    bal = USDC.functions.balanceOf(Web3.to_checksum_address(addr)).call()
    return from_wei_usdc(bal)


def ensure_eth_topup_internal(addr: str) -> Optional[str]:
    if get_eth_balance(addr) >= TOPUP_WEI:
        return None
    # send from paymaster
    nonce = w3.eth.get_transaction_count(Web3.to_checksum_address(PAYMASTER_ETH_ADDR))
    tx = {
        'to': Web3.to_checksum_address(addr),
        'value': TOPUP_WEI,
        'gas': 21000,
        'maxFeePerGas': w3.eth.gas_price,
        'maxPriorityFeePerGas': w3.eth.gas_price,
        'nonce': nonce,
        'chainId': CHAIN_ID,
    }
    signed = w3.eth.account.sign_transaction(tx, private_key=PAYMASTER_ETH_PRIV)
    txh = w3.eth.send_raw_transaction(signed.rawTransaction)
    r = w3.eth.wait_for_transaction_receipt(txh, timeout=120)
    time.sleep(10)  # global spacing rule
    return txh.hex()


def erc20_transfer(from_addr: str, from_priv: str, to_addr: str, amount_dec: Decimal) -> str:
    amount = to_wei_usdc(amount_dec)
    nonce = w3.eth.get_transaction_count(Web3.to_checksum_address(from_addr))
    txn = USDC.functions.transfer(Web3.to_checksum_address(to_addr), amount).build_transaction({
        'from': Web3.to_checksum_address(from_addr),
        'chainId': CHAIN_ID,
        'nonce': nonce,
        'maxFeePerGas': w3.eth.gas_price,
        'maxPriorityFeePerGas': w3.eth.gas_price,
        'gas': 120000,
    })
    signed = w3.eth.account.sign_transaction(txn, private_key=from_priv)
    txh = w3.eth.send_raw_transaction(signed.rawTransaction)
    w3.eth.wait_for_transaction_receipt(txh, timeout=180)
    time.sleep(10)  # global spacing rule
    return txh.hex()