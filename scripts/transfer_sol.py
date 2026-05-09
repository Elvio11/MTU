import sys
import os
import argparse

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from src.python.shared.keystore import Keystore
from solders.keypair import Keypair
from solders.pubkey import Pubkey
from solders.system_program import transfer, TransferParams as SystemTransferParams
from solders.transaction import VersionedTransaction
from solders.message import MessageV0
from solana.rpc.api import Client


def main():
    parser = argparse.ArgumentParser(description="Transfer SOL from encrypted keystore")
    parser.add_argument("--keystore", "-k", required=True, help="Path to keystore file")
    parser.add_argument("--passphrase", "-p", required=True, help="Keystore passphrase")
    parser.add_argument("--to", "-t", required=True, help="Recipient address")
    parser.add_argument(
        "--amount", "-a", type=float, required=True, help="Amount in SOL"
    )
    parser.add_argument(
        "--rpc", default="https://api.mainnet-beta.solana.com", help="RPC URL"
    )

    args = parser.parse_args()

    print(f"Loading keystore: {args.keystore}")
    keystore = Keystore(args.keystore)
    secret_bytes = keystore.load_keypair(args.passphrase)
    keypair = Keypair.from_bytes(secret_bytes)

    print(f"Wallet: {keypair.pubkey()}")

    client = Client(args.rpc)

    lamports = client.get_balance(keypair.pubkey())
    balance = lamports.value / 1e9
    print(f"Current balance: {balance:.9f} SOL")

    if balance < args.amount + 0.0005:
        print(
            f"ERROR: Insufficient balance! Need {args.amount + 0.0005:.9f} SOL, have {balance:.9f} SOL"
        )
        sys.exit(1)

    try:
        to_pubkey = Pubkey.from_string(args.to)
    except:
        print(f"ERROR: Invalid recipient address: {args.to}")
        sys.exit(1)

    print(f"\nTransferring {args.amount} SOL to {args.to}...")

    try:
        transfer_ix = transfer(
            SystemTransferParams(
                from_pubkey=keypair.pubkey(),
                to_pubkey=to_pubkey,
                lamports=int(args.amount * 1e9),
            )
        )

        resp = client.get_latest_blockhash()
        blockhash = resp.value.blockhash

        # Create a message with the instruction
        msg = MessageV0.try_compile(
            payer=keypair.pubkey(),
            instructions=[transfer_ix],
            address_lookup_table_accounts=[],
            recent_blockhash=blockhash,
        )

        txn = VersionedTransaction(msg, [keypair])

        result = client.send_transaction(txn)

        tx_signature = str(result.value)
        print(f"SUCCESS! Transaction: https://solscan.io/tx/{tx_signature}")
    except Exception as e:
        print(f"ERROR: Transfer failed: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
