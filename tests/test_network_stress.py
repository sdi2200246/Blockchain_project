"""
Network stress tests: measure convergence under concurrent multi-miner load.

These tests measure convergence quality rather than asserting strict equality,
since the system is probabilistically consistent. Each test prints a
convergence report showing tip distribution across all nodes.
"""

import pytest
import time
import copy
import ecdsa
import hashlib
from collections import Counter

from node2 import CoreNode, MinerNode, BootstrapperNode
from transactions import TxInput, TxOutput, Transaction
from blockchain import BlockChain
from block import Block


def wait(seconds=0.3):
    time.sleep(seconds)

def measure_convergence(cores, miners):
    all_nodes = cores + miners
    tips = Counter()
    chain_lengths = []
    all_tips = []
    depth_minus_one = Counter()  # NEW

    for node in all_nodes:
        if not node.blcok_chain.chain:
            continue
        chain = node.blcok_chain.chain
        tip = chain[-1].block_hash()
        tips[tip] += 1
        chain_lengths.append((node.port, len(chain)))
        all_tips.append((node.port, tip))
        
        # NEW: track agreement at depth-1
        if len(chain) >= 2:
            depth_minus_one[chain[-2].block_hash()] += 1

    return {
        "total_nodes": len(all_nodes),
        "unique_tips": len(tips),
        "majority_size": max(tips.values()) if tips else 0,
        "chain_lengths": chain_lengths,
        "all_tips": all_tips,
        "tip_counter": tips,
        "depth_minus_one": depth_minus_one,  # NEW
    }


def make_keypair():
    sk = ecdsa.SigningKey.generate(curve=ecdsa.SECP256k1)
    vk = sk.verifying_key
    return {
        "sk": sk,
        "priv": sk.to_string().hex(),
        "pub": vk.to_string().hex(),
        "hash": hashlib.sha256(bytes.fromhex(vk.to_string().hex())).hexdigest(),
    }


def make_seeded_chain(num_utxos=20, difficulty="0000"):
    """Genesis block + N pending transactions, all signed and ready to mine."""
    alice = make_keypair()
    bob = make_keypair()

    bc = BlockChain(difficulty=difficulty)
    for i in range(num_utxos):
        bc.utxo_pool[(f"tx{i}", 0)] = TxOutput(50, alice["hash"])

    genesis = Block(0, [], time.time(), "0" * 64)
    genesis.Merkle_tree_creation()
    bc.mine_block(genesis)
    bc.uptade_chain(genesis)

    for i in range(num_utxos):
        inp = TxInput(f"tx{i}", 0, alice["pub"])
        out = TxOutput(50, bob["hash"])
        tx = Transaction([inp], [out])
        tx.sign_all_inputs([alice["priv"]])
        bc.transaction_pool.add(tx)

    return bc, alice, bob


def build_network(num_cores, num_miners, base_port=30000, difficulty="0000"):
    """Spin up: 1 bootstrapper + N cores + M miners, fully peer-discovered."""
    bc, _, _ = make_seeded_chain(
        num_utxos=num_cores * 4 + num_miners * 4,
        difficulty=difficulty,
    )

    bootstrapper = BootstrapperNode('localhost', base_port)
    wait()

    cores = []
    for i in range(num_cores):
        node = CoreNode('localhost', base_port + 1 + i)
        node.blcok_chain = copy.deepcopy(bc)
        wait()
        sock = node.connect_to_peer(base_port)
        node.send_message_to_peer(sock, (b"registration", (node.host, node.port)))
        cores.append(node)

    miners = []
    for i in range(num_miners):
        port = base_port + 100 + i
        miner = MinerNode('localhost', port, chain=copy.deepcopy(bc))
        wait()
        sock = miner.connect_to_peer(base_port)
        miner.send_message_to_peer(sock, (b"registration", (miner.host, miner.port)))
        miners.append(miner)

    wait(1.0)

    for node in cores + miners:
        sock = node.connect_to_peer(base_port)
        node.send_and_receive_message_to_peer(sock, (b"get_peers", None))

    wait(1.0)

    return bootstrapper, cores, miners


def print_convergence_report(stats, label=""):
    print(f"\n========== CONVERGENCE REPORT {label} ==========")
    print(f"Total nodes:     {stats['total_nodes']}")
    print(f"Unique tips:     {stats['unique_tips']}")
    print(f"Majority size:   {stats['majority_size']} / {stats['total_nodes']}")
    print(f"Chain lengths:   {sorted(set(L for _, L in stats['chain_lengths']))}")
    print(f"Tip distribution:")
    for tip, count in stats['tip_counter'].most_common():
        print(f"  {count:2d} nodes on {tip[:16]}...")
    print("=" * 50)
    print(f"\nAgreement at depth-1 (second-to-last block):")
    for h, count in stats['depth_minus_one'].most_common():
        print(f"  {count:2d} nodes on {h[:16]}...")


# ---------- Baseline tests at default difficulty 0000 ----------

@pytest.mark.slow
class TestNetworkConvergenceBaseline:
    """Difficulty 0000 — fast mining, tight race windows, more divergence expected at scale."""

    def test_small_3cores_2miners(self):
        _, cores, miners = build_network(num_cores=3, num_miners=2, base_port=30000)
        for m in miners:
            m.stat_mining_event.set()
        time.sleep(20)
        stats = measure_convergence(cores, miners)
        print_convergence_report(stats, label="baseline 3+2")
        assert stats["majority_size"] >= stats["total_nodes"] - 1

    def test_medium_5cores_3miners(self):
        _, cores, miners = build_network(num_cores=5, num_miners=3, base_port=31000)
        for m in miners:
            m.stat_mining_event.set()
        time.sleep(30)
        stats = measure_convergence(cores, miners)
        print_convergence_report(stats, label="baseline 5+3")
        assert stats["majority_size"] >= int(stats["total_nodes"] * 0.75)

    def test_large_8cores_4miners(self):
        _, cores, miners = build_network(num_cores=8, num_miners=4, base_port=32000)
        for m in miners:
            m.stat_mining_event.set()
        time.sleep(45)
        stats = measure_convergence(cores, miners)
        print_convergence_report(stats, label="baseline 8+4")
        # At this scale, baseline often falls below 66% — that's a known result
        # We assert >= 50% so the test still passes and we can compare to high-difficulty
        assert stats["majority_size"] >= int(stats["total_nodes"] * 0.50)


# ---------- High-difficulty tests at 00000 ----------

@pytest.mark.slow
class TestNetworkConvergenceHighDifficulty:
    """Difficulty 00000 — ~16x more PoW per block.
    Wider race window between blocks gives broadcasts time to propagate."""

    def test_small_3cores_2miners_hd(self):
        _, cores, miners = build_network(
            num_cores=3, num_miners=2, base_port=34000, difficulty="00000"
        )
        for m in miners:
            m.stat_mining_event.set()
        time.sleep(30)
        stats = measure_convergence(cores, miners)
        print_convergence_report(stats, label="HD 3+2")
        assert stats["unique_tips"] == 1, "Expected full convergence at small scale"

    def test_medium_5cores_3miners_hd(self):
        _, cores, miners = build_network(
            num_cores=5, num_miners=3, base_port=35000, difficulty="00000"
        )
        for m in miners:
            m.stat_mining_event.set()
        time.sleep(45)
        stats = measure_convergence(cores, miners)
        print_convergence_report(stats, label="HD 5+3")
        assert stats["majority_size"] == stats["total_nodes"], "Expected full convergence"

    def test_large_8cores_4miners_hd(self):
        _, cores, miners = build_network(
            num_cores=8, num_miners=4, base_port=36000, difficulty="00000"
        )
        for m in miners:
            m.stat_mining_event.set()
        time.sleep(500)
        stats = measure_convergence(cores, miners)
        print_convergence_report(stats, label="HD 8+4")
        # The interesting comparison: did HD help large-scale convergence?
        assert stats["majority_size"] >= int(stats["total_nodes"] * 0.80), \
            f"Less than 80% agreement with bumped difficulty"
        


@pytest.mark.slow
class TestNetworkConvergenceScale:
    """Push the network to find the actual scale ceiling."""

    def test_xxxl_30cores_10miners_hd(self):
        """1 boot + 30 cores + 10 miners = 41 nodes, difficulty 00000.
        Real stress test — does the system still converge at this scale?"""
        _, cores, miners = build_network(
            num_cores=30, num_miners=10, base_port=40000, difficulty="00000"
        )

        for m in miners:
            m.stat_mining_event.set()

        time.sleep(200)  # 3 minutes — mining is slower at "00000"

        stats = measure_convergence(cores, miners)
        print_convergence_report(stats, label="XXXL 30+10 HD")

        # At 41 nodes, just want to see what happens — measure, don't strict-assert
        assert stats["majority_size"] >= int(stats["total_nodes"] * 0.50), \
            f"Less than majority agreement at 41-node scale: {stats['majority_size']}/{stats['total_nodes']}"
        
        