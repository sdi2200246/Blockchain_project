import ecdsa
import hashlib
import json
import time


class TxInput:
    def __init__(self, prev_txid, output_index, pubkey, signature=None):
        self.prev_txid = prev_txid
        self.output_index = output_index
        self.pubkey = pubkey  # in hex string
        self.signature = signature  # in hex string or None

    def pubkey_hash(self):
        return hashlib.sha256(bytes.fromhex(self.pubkey)).hexdigest()

    def to_dict(self, include_signature=True):
        d = {
            "prev_txid": self.prev_txid,
            "output_index": self.output_index,
            "pubkey": self.pubkey
        }
        if include_signature:
            d["signature"] = self.signature
        return d

    def sign(self, tx_bytes, private_key_hex):
        sk = ecdsa.SigningKey.from_string(bytes.fromhex(private_key_hex), curve=ecdsa.SECP256k1)
        self.signature = sk.sign(tx_bytes).hex()

    def verify_signature(self, tx_bytes):
        try:
            vk = ecdsa.VerifyingKey.from_string(bytes.fromhex(self.pubkey), curve=ecdsa.SECP256k1)
            return vk.verify(bytes.fromhex(self.signature), tx_bytes)
        except ecdsa.BadSignatureError:
            return False
        
    def __str__(self):
        return f"TxInput(prev_txid={self.prev_txid}, output_index={self.output_index}, pubkey={self.pubkey}, signature={self.signature})"

    __repr__ = __str__

class TxOutput:
    def __init__(self, value, recipient_pubkey_hash):
        self.value = value
        self.recipient = recipient_pubkey_hash  # SHA256(pubkey) in hex

    def __str__(self):
        return f"TxOutput(amount={self.value}, recipient_hash={self.recipient[:10]})"

    __repr__ = __str__

    def to_dict(self):
        return {
            "value": self.value,
            "recipient": self.recipient
        }

class Transaction:
    def __init__(self, inputs: list, outputs: list, timestamp=None):
        self.inputs = inputs
        self.outputs = outputs
        self.timestamp = timestamp or time.time()

    def __eq__(self, other):
        if not isinstance(other, Transaction):
            return False
        return self.get_tx_id() == other.get_tx_id()

    def __hash__(self):
        return hash(self.get_tx_id())


    def to_dict(self, include_signatures=True):
        return {
            "inputs": [inp.to_dict(include_signature=include_signatures) for inp in self.inputs],
            "outputs": [out.to_dict() for out in self.outputs],
            "timestamp": self.timestamp
        }

    def to_bytes(self, include_signatures=True):
        tx_data = self.to_dict(include_signatures=include_signatures)
        return json.dumps(tx_data, sort_keys=True).encode('utf-8')

    def sign_all_inputs(self, private_keys):
        """
        Signs the transaction's inputs using the corresponding private keys.
        Each private key must match the input's public key.
        `private_keys` is a list aligned with self.inputs.
        """
        tx_preimage = self.to_bytes(include_signatures=False)
        for inp, priv_key in zip(self.inputs, private_keys):
            inp.sign(tx_preimage, priv_key)

    def verify_all_signatures(self):
        tx_preimage = self.to_bytes(include_signatures=False)
        return all(inp.verify_signature(tx_preimage) for inp in self.inputs)

    def get_tx_id(self):
        tx_string = self.to_bytes(include_signatures=False)
        return hashlib.sha256(tx_string).hexdigest()

    def __str__(self):
        tx_dict = self.to_dict(include_signatures=True)
        tx_dict["tx_id"] = self.get_tx_id()
        return json.dumps(tx_dict, indent=2)

    __repr__ = __str__