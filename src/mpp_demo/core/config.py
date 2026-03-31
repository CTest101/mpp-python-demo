"""Shared configuration for Tempo and MPP protocol.

基于 pympp 0.5.0 真实常量。
"""

import os

from mpp.methods.tempo import TESTNET_CHAIN_ID, PATH_USD

# Tempo Moderato Testnet (真实测试网)
TEMPO_CHAIN_ID = TESTNET_CHAIN_ID  # 42431
TEMPO_RPC = "https://rpc.moderato.tempo.xyz"

# pathUSD — Tempo 默认稳定币
PATH_USD_ADDRESS = PATH_USD  # 0x20c0...

# Server
SERVER_HOST = os.getenv("MPP_SERVER_HOST", "http://localhost:8000")
SERVER_PORT = int(os.getenv("MPP_SERVER_PORT", "8000"))

# 收款地址
RECIPIENT = os.getenv("MPP_RECIPIENT", "")

# 定价
CHARGE_AMOUNT = "0.01"       # $0.01 per joke
SESSION_AMOUNT = "0.005"     # $0.005 per gallery image
