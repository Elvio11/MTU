import struct
import base64
from typing import Dict, Any, Optional

# Pump.fun Bonding Curve Layout (Borsh)
# Discriminator: 8 bytes
# virtualTokenReserves: u64
# virtualQuoteReserves: u64
# realTokenReserves: u64
# realQuoteReserves: u64
# tokenTotalSupply: u64
# complete: bool

BONDING_CURVE_LAYOUT = "<8sQQQQQB"
INITIAL_REAL_TOKEN_RESERVES = 793100000000000  # 793.1M * 10^6

def decode_bonding_curve(data_base64: str) -> Optional[Dict[str, Any]]:
    """Decode base64 bonding curve account data into a dictionary"""
    try:
        data = base64.b64decode(data_base64)
        if len(data) < 49: # 8 + 8*5 + 1
            return None
            
        unpacked = struct.unpack(BONDING_CURVE_LAYOUT, data[:struct.calcsize(BONDING_CURVE_LAYOUT)])
        
        return {
            "virtualTokenReserves": unpacked[1],
            "virtualQuoteReserves": unpacked[2],
            "realTokenReserves": unpacked[3],
            "realQuoteReserves": unpacked[4],
            "tokenTotalSupply": unpacked[5],
            "complete": bool(unpacked[6])
        }
    except Exception as e:
        print(f"[BONDING_CURVE] Error decoding: {e}")
        return None

def calculate_progress(real_token_reserves: int) -> float:
    """Calculate the bonding curve progress percentage"""
    if real_token_reserves <= 0:
        return 100.0
        
    # Progress = 100 - ((realTokenReserves * 100) / initialRealTokenReserves)
    progress = 100.0 - ((real_token_reserves * 100.0) / INITIAL_REAL_TOKEN_RESERVES)
    return max(0.0, min(100.0, progress))

def get_bonding_curve_pda(mint_address: str, program_id: str = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P") -> str:
    """
    Find the Bonding Curve PDA for a given mint.
    Logic: find_program_address(['bonding-curve', mint_pubkey], program_id)
    Note: This is a simplified representation. Actual PDA derivation requires solana-py.
    """
    return "" # Placeholder for now, as we usually get this from the trade events.
