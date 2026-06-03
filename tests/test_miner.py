import pytest
import time
import ecdsa
import hashlib
import copy

from node2 import MinerNode, CoreNode, BootstrapperNode
from transactions import TxInput, TxOutput, Transaction
from blockchain import BlockChain
from block import Block


def wait(seconds=0.3):
    time.sleep(seconds)


def wait_for(condition_fn, timeout=15.0, interval=0.1):
    """Poll until condition is True or timeout expires.
    Returns True if condition met, False if timed out."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if condition_fn():
            return True
        time.sleep(interval)
    return False


def make_keypair():
    sk = ecdsa.SigningKey.generate(curve=ecdsa.SECP256k1)
    vk = sk.verifying_key
    priv = sk.to_string().hex()
    pub = vk.to_string().hex()
    pubkey_hash = hashlib.sha256(bytes.fromhex(pub)).hexdigest()
    return {"sk": sk, "priv": priv, "pub": pub, "hash": pubkey_hash}


def make_chain_with_pending_txs(num_txs=4):
    """Genesis block + N signed pending transactions, ready for a miner."""
    alice = make_keypair()
    bob = make_keypair()

    bc = BlockChain()

    for i in range(num_txs):
        bc.utxo_pool[(f"tx{i}", 0)] = TxOutput(50, alice["hash"])

    genesis = Block(0, [], time.time(), "0" * 64)
    genesis.Merkle_tree_creation()
    bc.mine_block(genesis)
    bc.uptade_chain(genesis)

    for i in range(num_txs):
        inp = TxInput(f"tx{i}", 0, alice["pub"])
        out = TxOutput(50, bob["hash"])
        tx = Transaction([inp], [out])
        tx.sign_all_inputs([alice["priv"]])
        bc.transaction_pool.add(tx)

    return bc, alice, bob


# ---------- Single miner tests ----------

class TestMinerSolo:
    def test_miner_does_not_mine_when_pool_too_small(self):
        """create_candidate_block requires >= 2 txs.
        With only 1 tx, the miner clears the event and waits."""
        bc, alice, bob = make_chain_with_pending_txs(num_txs=4)
        # Strip down to 1 transaction
        txs = list(bc.transaction_pool)
        bc.transaction_pool = {txs[0]}

        miner = MinerNode('localhost', 24001, chain=bc)
        wait()

        chain_len_before = len(miner.blcok_chain.chain)
        miner.stat_mining_event.set()
        time.sleep(1.0)  # let miner wake, check, give up

        assert len(miner.blcok_chain.chain) == chain_len_before
        assert not miner.stat_mining_event.is_set()

    def test_miner_mines_one_block_when_triggered(self):
        bc, _, _ = make_chain_with_pending_txs(num_txs=2)
        miner = MinerNode('localhost', 24002, chain=bc)
        wait()

        assert len(miner.blcok_chain.chain) == 1  # only genesis
        miner.stat_mining_event.set()

        grew = wait_for(lambda: len(miner.blcok_chain.chain) >= 2, timeout=15.0)
        assert grew, "Miner did not produce a block within 15s"
        assert len(miner.blcok_chain.chain) == 2

    def test_miner_block_satisfies_difficulty(self):
        bc, _, _ = make_chain_with_pending_txs(num_txs=2)
        miner = MinerNode('localhost', 24003, chain=bc)
        wait()

        miner.stat_mining_event.set()
        wait_for(lambda: len(miner.blcok_chain.chain) >= 2, timeout=15.0)

        new_block = miner.blcok_chain.chain[-1]
        assert new_block.block_hash().startswith(miner.blcok_chain.difficulty)

    def test_miner_removes_included_txs_from_pool(self):
        bc, _, _ = make_chain_with_pending_txs(num_txs=2)
        miner = MinerNode('localhost', 24004, chain=bc)
        wait()

        miner.stat_mining_event.set()
        wait_for(lambda: len(miner.blcok_chain.chain) >= 2, timeout=15.0)

        new_block = miner.blcok_chain.chain[-1]
        for tx in new_block.transactions:
            assert tx not in miner.blcok_chain.transaction_pool

    def test_miner_updates_utxo_pool(self):
        """After mining, spent UTXOs are removed and new ones created."""
        bc, _, _ = make_chain_with_pending_txs(num_txs=2)

        # Snapshot which UTXOs exist before
        utxos_before = set(bc.utxo_pool.keys())

        miner = MinerNode('localhost', 24005, chain=bc)
        wait()

        miner.stat_mining_event.set()
        wait_for(lambda: len(miner.blcok_chain.chain) >= 2, timeout=15.0)

        new_block = miner.blcok_chain.chain[-1]

        # Each input's prev_txid+output_index should be gone from utxo_pool
        for tx in new_block.transactions:
            for inp in tx.inputs:
                key = (inp.prev_txid, inp.output_index)
                assert key not in miner.blcok_chain.utxo_pool, \
                    f"Spent UTXO {key} still in pool"

        # New outputs should be in the pool
        for tx in new_block.transactions:
            tx_id = tx.get_tx_id()
            for idx in range(len(tx.outputs)):
                assert (tx_id, idx) in miner.blcok_chain.utxo_pool


# ---------- Miner + CoreNode propagation ----------

class TestMinerPropagation:
    def test_miner_broadcasts_mined_block_to_core_node(self):
        """A miner mines a block; a connected CoreNode receives it
        and appends it to its own chain."""
        bc, _, _ = make_chain_with_pending_txs(num_txs=2)

        miner = MinerNode('localhost', 25001, chain=copy.deepcopy(bc))
        core = CoreNode('localhost', 25002)
        core.blcok_chain = copy.deepcopy(bc)
        wait()

        # Wire them up: miner knows about core
        miner.peers.add(('localhost', 25002))

        assert len(core.blcok_chain.chain) == 1
        miner.stat_mining_event.set()

        # Wait for the core node's chain to grow (proves the broadcast was received)
        propagated = wait_for(
            lambda: len(core.blcok_chain.chain) >= 2, timeout=20.0
        )
        assert propagated, \
            f"Core node's chain did not grow. Miner chain: {len(miner.blcok_chain.chain)}, " \
            f"Core chain: {len(core.blcok_chain.chain)}"

        # The block on the core node should match what the miner produced
        assert core.blcok_chain.chain[-1].block_hash() == \
               miner.blcok_chain.chain[-1].block_hash()


# ---------- Two miners ----------

class TestTwoMiners:
    def test_two_miners_eventually_agree(self):
        """Two miners with the same starting chain, mining concurrently,
        should end up on the same chain (assuming the fork-resolution path
        works). This test is somewhat flaky due to the broadcast race bug
        — it's here to document the *intended* behavior."""
        bc, _, _ = make_chain_with_pending_txs(num_txs=4)

        miner1 = MinerNode('localhost', 26001, chain=copy.deepcopy(bc))
        miner2 = MinerNode('localhost', 26002, chain=copy.deepcopy(bc))
        wait()

        miner1.peers.add(('localhost', 26002))
        miner2.peers.add(('localhost', 26001))

        miner1.stat_mining_event.set()
        miner2.stat_mining_event.set()

        # Give them plenty of time to mine + reconcile
        time.sleep(15.0)

        tip1 = miner1.blcok_chain.chain[-1].block_hash()
        tip2 = miner2.blcok_chain.chain[-1].block_hash()

        assert tip1 == tip2, (
            f"Miners disagree on tip:\n"
            f"  miner1 (port 26001): {tip1}\n"
            f"  miner2 (port 26002): {tip2}\n"
            f"  miner1 chain length: {len(miner1.blcok_chain.chain)}\n"
            f"  miner2 chain length: {len(miner2.blcok_chain.chain)}"
        )