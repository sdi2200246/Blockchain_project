# Blockchain Prototype

A from-scratch blockchain implementation in Python — UTXO model, ECDSA signatures, Merkle trees, Proof-of-Work mining, and a multi-threaded P2P network with custom wire protocol and fork resolution.

Built as a learning project to internalize the core mechanics of distributed consensus, peer-to-peer messaging, and cryptographic transaction validation without leaning on any blockchain library.

---

## What's Implemented

**Cryptography & Transactions**
- ECDSA (SECP256k1) key pairs for identity and signing
- SHA-256 hashing throughout (transaction IDs, block hashes, pubkey hashes)
- Bitcoin-style **UTXO model**: transactions consume previous outputs and produce new ones
- Multi-input, multi-output transactions with per-input signatures
- Double-spend detection within a transaction

**Blocks & Merkle Trees**
- Deterministic block serialization (sorted JSON) for stable hashing
- Merkle tree construction over block transactions
- Merkle inclusion proofs (`get_merkle_proof`) and verification (`transaction_verification`)

**Consensus**
- Proof-of-Work mining with adjustable difficulty (hash prefix target)
- Block validation: link integrity, PoW satisfaction, transaction validity, seen-block deduplication
- Chain validation: re-derives each block hash to verify the link structure
- Longest-chain rule and fork resolution on conflicting blocks

**P2P Network**
- TCP socket-based peer-to-peer messaging
- Three node roles via inheritance: `BootstrapperNode` → `CoreNode` → `MinerNode`
- Custom binary wire protocol (fixed header + length-prefixed pickle payload)
- Transaction and block broadcast across the peer set
- Bootstrapper-mediated peer discovery

**Concurrency**
- Per-connection handler threads
- Worker thread consuming a job queue for ordered message processing
- Mining thread gated by a `threading.Event` — only runs when there's enough work
- `threading.Lock` on the chain to coordinate mining vs. incoming-block updates
- Mid-mining fork detection: compares chain head before and after PoW

---

## Architecture

```
┌─────────────────────┐         ┌─────────────────────┐
│   BootstrapperNode  │◄────────┤      CoreNode       │
│  (peer registry)    │ register│  (validate & relay) │
└─────────────────────┘         └──────────┬──────────┘
                                            │ inherits
                                            ▼
                                ┌─────────────────────┐
                                │      MinerNode      │
                                │  (build candidate,  │
                                │   PoW, broadcast)   │
                                └─────────────────────┘
```

**Node responsibilities**

| Node               | Role                                                                  |
|--------------------|-----------------------------------------------------------------------|
| `BootstrapperNode` | Tracks the peer set. Hands out peer lists on `get_peers`.             |
| `CoreNode`         | Validates and relays transactions and blocks. Resolves forks.         |
| `MinerNode`        | All of CoreNode + selects pending txs, runs PoW, broadcasts new blocks.|

---

## Concurrency Model

Each node runs three concurrent loops:

1. **Listener thread** — `receive_requests_loop` accepts TCP connections and dispatches each to a per-connection handler thread.
2. **Worker thread** — consumes `self.jobs` (a `queue.Queue`) and invokes the registered handler for each message type. This serializes state mutations through a single thread per node, even though network I/O is parallel.
3. **Miner thread** (MinerNode only) — waits on `stat_mining_event`. When the transaction pool has enough entries, it builds a candidate block, runs PoW under the chain lock, then re-checks the chain head before committing — if a competing block arrived during mining, the work is discarded.

The `chain_lock` ensures that the chain, UTXO pool, and transaction pool are never read or mutated by mining and message-handling threads simultaneously.

---

## Wire Protocol

Every message on the wire follows the same frame:

```
┌──────────────────┬──────────────┬──────────────────┐
│ 25-byte header   │ 4-byte length│ pickled payload  │
│ (message type)   │ (big-endian) │ (variable)       │
└──────────────────┴──────────────┴──────────────────┘
```

The header is null-padded to a fixed 25 bytes so the receiver can read it without knowing the message in advance. A length prefix then tells it exactly how many payload bytes to expect — `recv_exact` loops on `recv` until that many bytes have arrived, handling partial reads correctly.

**Supported message types**

| Header          | Direction         | Payload                  | Purpose                              |
|-----------------|-------------------|--------------------------|--------------------------------------|
| `registration`  | node → bootstrap  | `(host, port)`           | Join the network                     |
| `get_peers`     | node → bootstrap  | —                        | Request peer list                    |
| `peers`         | bootstrap → node  | `set[(host, port)]`      | Reply with peer set                  |
| `get_chain`     | node → node       | —                        | Request full chain                   |
| `new_chain`     | node → node       | `BlockChain`             | Send full chain (used for sync/fork) |
| `transaction`   | node → all peers  | `Transaction`            | Broadcast a pending transaction      |
| `block`         | node → all peers  | `Block`                  | Broadcast a newly mined block        |

---

## Running It

**Requirements**

```bash
pip install -r requirments.txt
```

(`ecdsa`, `pytest`)

**Run the tests**

```bash
pytest test_blockchain.py -v
```

The test suite covers transaction validation, single-node mining, multi-node chain sync via direct connection, peer discovery through a bootstrapper, transaction propagation across nodes, miner gating on transaction-pool size, block propagation across multiple core nodes, and concurrent mining by multiple miners producing forks.

---

## Design Notes

- **UTXO over account balance.** UTXO is closer to how production blockchains work and forces the validation logic to handle ownership, double-spending, and change outputs explicitly.
- **Single worker thread per node.** All state-mutating handlers run on one thread, avoiding most of the locking complexity that would otherwise be needed across the UTXO pool, transaction pool, and chain.
- **Mid-mining fork check.** After PoW completes, the miner re-acquires the chain lock and verifies that the head is still the one it built on. This prevents committing stale blocks when a competing block arrived during the PoW search.
- **Pickle on the wire.** Convenient for a learning project, but unsafe across untrusted peers — a real protocol would use a defined schema (protobuf, msgpack, custom binary) without arbitrary code execution.

## Limitations

This is a learning prototype, not production code.

- No transaction fees, no coinbase reward, no halving
- Fixed difficulty (no retargeting)
- No mempool eviction policy beyond "remove on inclusion"
- Pickle-based serialization on the wire (insecure for adversarial settings)
- No persistence — chain lives only in memory
- No DoS protection on the listener
