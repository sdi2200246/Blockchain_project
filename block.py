import json
import hashlib
import time
from transactions import Transaction ,TxOutput,TxInput
import ecdsa

class Block:
    def __init__(self, index, transactions:list[Transaction],timestamp, previous_hash, nonce=0 , merkle_tree = None):
        self.index = index
        self.transactions = transactions
        self.timestamp = timestamp
        self.previous_hash = previous_hash
        self.nonce = nonce
        self.merkle_tree = merkle_tree

    def block_to_dict(self):
        return {
            "index": self.index,
            "timestamp": self.timestamp,
            "previous_hash": self.previous_hash,
            "nonce": self.nonce,
            "merkle_root": self.merkle_tree,
            "transactions":[dic.to_dict() for dic in self.transactions]
        }

    def block_hash(self):
        block_dict = self.block_to_dict()
        block_string = json.dumps(block_dict, sort_keys=True).encode()
        return hashlib.sha256(block_string).hexdigest()

    @staticmethod
    def hash_data(data):
        if isinstance(data, bytes):
            return hashlib.sha256(data).hexdigest()
        return hashlib.sha256(data.encode('utf-8')).hexdigest()

    def get_merkle_proof(self, tx:Transaction):
        leaf_hashes = [self.hash_data(t.to_bytes()) for t in self.transactions]

        try:
            index = leaf_hashes.index(self.hash_data(tx.to_bytes()))
        except ValueError:
            return None  # Transaction not found

        proof = []
        current_level = leaf_hashes

        while len(current_level) > 1:
            if len(current_level) % 2 != 0:
                current_level.append(current_level[-1])

            sibling_index = index ^ 1  # Get sibling index
            position = "right" if index % 2 == 0 else "left"
            proof.append({
                "hash": current_level[sibling_index],
                "position": position
            })

            index = index // 2
            next_level = []

            for i in range(0, len(current_level), 2):
                combined = self.hash_data(current_level[i] + current_level[i + 1])
                next_level.append(combined)

            current_level = next_level

        return proof


    def transaction_verification(self, leaf_hash: str, proof: list) -> bool:

        hash = leaf_hash

        for sibling in proof:

            if sibling["position"] == "right":
                hash = self.hash_data(hash + sibling["hash"])

            else : hash = self.hash_data(sibling["hash"] + hash)
              
        return hash == self.merkle_tree


    def Merkle_tree_creation(self):
        if not self.transactions:
            self.merkle_tree = self.hash_data(b"")
            return

        current_level = [self.hash_data(tx.to_bytes()) for tx in self.transactions]

        while len(current_level) > 1:
            # If odd number, duplicate last hash
            if len(current_level) % 2 != 0:
                current_level.append(current_level[-1])

            next_level = []
            # Step 2: Hash pairs
            for i in range(0, len(current_level), 2):
                combined_hash = self.hash_data(current_level[i] + current_level[i+1])
                next_level.append(combined_hash)

            current_level = next_level

        # Step 3: Merkle root
        self.merkle_tree = current_level[0]
