import pytest
import ecdsa
import hashlib
from transactions import TxOutput, TxInput, Transaction
from blockchain import BlockChain
from block import Block
import time


def make_keypair():
    sk = ecdsa.SigningKey.generate(curve=ecdsa.SECP256k1)
    vk = sk.verifying_key
    priv = sk.to_string().hex()
    pub = vk.to_string().hex()
    pubkey_hash = hashlib.sha256(bytes.fromhex(pub)).hexdigest()
    return {"sk": sk, "priv": priv, "pub": pub, "hash": pubkey_hash}


@pytest.fixture
def alice():
    return make_keypair()


@pytest.fixture
def bob():
    return make_keypair()


@pytest.fixture
def empty_chain():
    """A fresh blockchain with no blocks, no UTXOs."""
    return BlockChain()


@pytest.fixture
def chain_with_utxos(alice):
    """A blockchain seeded with 5 UTXOs of 50 coins each, all owned by alice."""
    bc = BlockChain()
    for i in range(5):
        bc.utxo_pool[(f"tx{i}", 0)] = TxOutput(50, alice["hash"])
    return bc


@pytest.fixture
def chain_with_genesis(chain_with_utxos):
    """chain_with_utxos plus a mined genesis block."""
    genesis = Block(0, [], time.time(), "0" * 64)
    genesis.Merkle_tree_creation()
    chain_with_utxos.mine_block(genesis)
    chain_with_utxos.uptade_chain(genesis)
    return chain_with_utxos


def make_tx(from_kp, to_kp, amount, prev_txid, output_index):
    """Helper to build and sign a single-input single-output tx."""
    inp = TxInput(prev_txid, output_index, from_kp["pub"])
    out = TxOutput(amount, to_kp["hash"])
    tx = Transaction([inp], [out])
    tx.sign_all_inputs([from_kp["priv"]])
    return tx