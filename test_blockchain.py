import pytest
from transactions import TxOutput , TxInput , Transaction
from blockchain import BlockChain , Block
from node2 import CoreNode , BootstrapperNode , MinerNode
import ecdsa
import hashlib
import time
import copy

def wait():
    time.sleep(0.3)

def generate_keypair():
    sk = ecdsa.SigningKey.generate(curve=ecdsa.SECP256k1)
    vk = sk.verifying_key
    priv = sk.to_string().hex()
    pub = vk.to_string().hex()
    hashed = hashlib.sha256(bytes.fromhex(pub)).hexdigest()
    return sk, vk, priv, pub, hashed


@pytest.fixture
def setup_blockchain():
    bc = BlockChain()

    sk_alice, _, priv_alice, pub_alice, hash_alice = generate_keypair()
    sk_bob, _, priv_bob, pub_bob, hash_bob = generate_keypair()

    bc.utxo_pool[("tx0", 0)] = TxOutput(50, hash_alice)
    bc.utxo_pool[("tx1", 0)] = TxOutput(50, hash_alice)

    return bc, sk_alice, pub_alice, priv_alice, hash_alice, sk_bob, pub_bob, priv_bob, hash_bob

@pytest.fixture
def setup_blockchain_for_mining():
    bc = BlockChain()

    # --- Key generation ---
    sk_alice, _, priv_alice, pub_alice, hash_alice = generate_keypair()
    sk_bob, _, priv_bob, pub_bob, hash_bob = generate_keypair()

    # --- Step 1: Add UTXOs to Alice so she can spend ---
    bc.utxo_pool[("tx0", 0)] = TxOutput(50, hash_alice)
    bc.utxo_pool[("tx1", 0)] = TxOutput(50, hash_alice)
    bc.utxo_pool[("tx2", 0)] = TxOutput(50, hash_alice)
    bc.utxo_pool[("tx3", 0)] = TxOutput(50, hash_alice)
    bc.utxo_pool[("tx4", 0)] = TxOutput(50, hash_alice)
    bc.utxo_pool[("tx5", 0)] = TxOutput(50, hash_alice)
    bc.utxo_pool[("tx6", 0)] = TxOutput(50, hash_alice)
    bc.utxo_pool[("tx7", 0)] = TxOutput(50, hash_alice)
    bc.utxo_pool[("tx8", 0)] = TxOutput(50, hash_alice)
    bc.utxo_pool[("tx9", 0)] = TxOutput(50, hash_alice)


    # --- Step 2: Create initial valid transactions from Alice to Bob ---
    for i in range(10):  # Two initial txs to seed the pool
        tx_input = TxInput(f"tx{i}", 0, pub_alice)
        tx_output = TxOutput(50, hash_bob)
        tx = Transaction([tx_input], [tx_output])
        tx.sign_all_inputs([priv_alice])
        assert bc.validate_transaction(tx)
        bc.transaction_pool.add(tx)

    # --- Step 3: Create and mine genesis block (empty) ---
    genesis = Block(0, [], time.time(), "0" * 64)
    genesis.Merkle_tree_creation()
    bc.mine_block(genesis)
    bc.update_utxo_pool(genesis)
    bc.uptade_transaction_pool(genesis)
    bc.uptade_chain(genesis)

    # --- Step 4: Let miner mine valid transactions already in the pool ---
    return bc, sk_alice, pub_alice, priv_alice, hash_alice, sk_bob, pub_bob, priv_bob, hash_bob



def test_valid_transaction(setup_blockchain):
    bc, sk_alice, pub_alice, priv_alice, hash_alice, _, _, _, hash_bob = setup_blockchain

    inp1 = TxInput("tx0", 0, pub_alice)
    inp2 = TxInput("tx1", 0, pub_alice)
    out = TxOutput(100, hash_bob)

    tx = Transaction([inp1, inp2], [out])
    tx.sign_all_inputs([priv_alice, priv_alice])

    assert bc.validate_transaction(tx)
    assert tx in bc.transaction_pool

def test_valid_block(setup_blockchain):
    bc, sk_alice, pub_alice, priv_alice, hash_alice, _, _, _, hash_bob = setup_blockchain

    # Manually create and add the genesis block
    genesis_block = Block(
        index=0,
        previous_hash='0' * 64,
        transactions=[],
        nonce=0,
        timestamp=time.time()
    )
    bc.chain.append(genesis_block)

    # Now continue with the rest of the test
    inp1 = TxInput("tx0", 0, pub_alice)
    inp2 = TxInput("tx1", 0, pub_alice)
    out = TxOutput(100, hash_bob)

    tx = Transaction([inp1, inp2], [out])
    tx.sign_all_inputs([priv_alice, priv_alice])

    assert bc.validate_transaction(tx)

    block = Block(
        index=1,
        previous_hash=genesis_block.block_hash(),
        transactions=[tx],
        nonce=0,
        timestamp=time.time()
    )
    bc.mine_block(block)
    assert bc.block_validation(block)


def test_invalid_block(setup_blockchain):
    bc, sk_alice, pub_alice, priv_alice, hash_alice, _, _, _, hash_bob = setup_blockchain

    # Manually create and add the genesis block
    genesis_block = Block(
        index=0,
        previous_hash='0' * 64,
        transactions=[],
        nonce=0,
        timestamp=time.time()
    )
    bc.chain.append(genesis_block)

    # Now continue with the rest of the test
    inp1 = TxInput("tx0", 0, pub_alice)
    inp2 = TxInput("tx1", 0, pub_alice)
    out = TxOutput(100, hash_bob)

    tx = Transaction([inp1, inp2], [out])
    tx.sign_all_inputs([priv_alice, priv_alice])

    # assert bc.validate_transaction(tx)

    block = Block(
        index=1,
        previous_hash=genesis_block.block_hash(),
        transactions=[tx],
        nonce=0,
        timestamp=time.time()
    )

    assert not bc.block_validation(block)


def test_invalid_transaction_wrong_signature(setup_blockchain):
    bc, _, _, _, _, sk_bob, pub_bob, priv_bob, hash_bob = setup_blockchain

    inp = TxInput("tx0", 0, pub_bob)  # Bob tries to use Alice's UTXO
    out = TxOutput(50, hash_bob)

    tx = Transaction([inp], [out])
    tx.sign_all_inputs([priv_bob])  # Incorrect signing key

    assert not bc.validate_transaction(tx)


def test_mining_and_chain_validation(setup_blockchain):
    bc, sk_alice, pub_alice, priv_alice, hash_alice, _, _, _, hash_bob = setup_blockchain
    # First transaction and block
    inp1 = TxInput("tx0", 0, pub_alice)
    out1 = TxOutput(50, hash_bob)
    tx1 = Transaction([inp1], [out1])
    tx1.sign_all_inputs([priv_alice])
    #assert bc.validate_transaction(tx1)
    block1 = Block(0, [tx1], time.time(), "0" * 64)  # Genesis prev hash or zeros
    block1.Merkle_tree_creation()
    bc.mine_block(block1)
    # Update UTXO pool or simulate as needed (optional for test completeness)
    # Second transaction and block
    # Use tx1's output as UTXO for the next transaction
    inp2 = TxInput(block1.block_hash(), 0, pub_alice)  # assuming block hash as txid for test
    out2 = TxOutput(50, hash_bob)
    tx2 = Transaction([inp2], [out2])
    tx2.sign_all_inputs([priv_alice])
    #assert bc.validate_transaction(tx2)
    block2 = Block(1, [tx2], time.time(), block1.block_hash())
    block2.Merkle_tree_creation()
    bc.mine_block(block2)
    # Assertions
    assert len(bc.chain) == 2
    assert bc.chain_validation()

def test_mining_and_chain_validation2(setup_blockchain):
    bc, sk_alice, pub_alice, priv_alice, hash_alice, _, _, _, hash_bob = setup_blockchain
    
    # --- First transaction and block ---
    inp1 = TxInput("tx0", 0, pub_alice)  # coinbase-like or dummy input for genesis (adjust as needed)
    out1 = TxOutput(50, hash_bob)
    tx1 = Transaction([inp1], [out1])
    tx1.sign_all_inputs([priv_alice])
    
    assert bc.validate_transaction(tx1)
    
    block1 = Block(0, [tx1], time.time(), "0" * 64)  # Genesis block with zero prev hash
    block1.Merkle_tree_creation()
    bc.mine_block(block1)
    
    # Update UTXO pool after mining block1
    bc.update_utxo_pool(block1)
    

    # --- Second transaction and block ---
    # Use tx1's tx_id as the previous output reference (UTXO)
    tx1_id = tx1.get_tx_id()
    inp2 = TxInput("tx1", 0, pub_alice)  # correct tx_id reference
    out2 = TxOutput(50, hash_bob)
    tx2 = Transaction([inp2], [out2])
    tx2.sign_all_inputs([priv_alice])
    
    assert bc.validate_transaction(tx2)
    
    block2 = Block(1, [tx2], time.time(), block1.block_hash())
    block2.Merkle_tree_creation()
    bc.mine_block(block2)
    
    # Update UTXO pool after mining block2
    bc.update_utxo_pool(block2)
    
    # --- Assertions ---
    assert len(bc.chain) == 2
    assert bc.chain_validation()
    
    # Check UTXO pool state:
    # The UTXO spent in tx2 (tx1's output) should be removed
    spent_utxo = ("tx1", 0)
    assert spent_utxo not in bc.utxo_pool
    
    # The new UTXO created by tx2 should be in the pool
    tx2_id = tx2.get_tx_id()
    new_utxo = (tx2_id, 0)
    assert new_utxo in bc.utxo_pool
    assert bc.utxo_pool[new_utxo].value == 50



def test_mining_and_chain_validation3(setup_blockchain):
    bc, sk_alice, pub_alice, priv_alice, hash_alice, sk_bob, pub_bob, priv_bob, hash_bob = setup_blockchain

    # --- tx1: Alice sends 50 coins to Bob ---
    inp1 = TxInput("tx0", 0, pub_alice)  # genesis input, dummy string kept
    out1 = TxOutput(50, hash_bob)
    tx1 = Transaction([inp1], [out1])
    tx1.sign_all_inputs([priv_alice])

    assert bc.validate_transaction(tx1)

    block1 = Block(0, [tx1], time.time(), "0" * 64)
    block1.Merkle_tree_creation()
    bc.mine_block(block1)
    bc.update_utxo_pool(block1)

    # --- tx2: Bob sends 50 coins back to Alice ---
    tx1_id = tx1.get_tx_id()
    inp2 = TxInput(tx1_id, 0, pub_bob)  # Use the real tx1 hash
    out2 = TxOutput(50, hash_alice)
    tx2 = Transaction([inp2], [out2])
    tx2.sign_all_inputs([priv_bob])

    assert bc.validate_transaction(tx2)

    block2 = Block(1, [tx2], time.time(), block1.block_hash())
    block2.Merkle_tree_creation()
    bc.mine_block(block2)
    bc.update_utxo_pool(block2)

    # --- Assertions ---
    assert len(bc.chain) == 2
    assert bc.chain_validation()

    # The UTXO from tx1 should be spent
    assert (tx1_id, 0) not in bc.utxo_pool

    # The UTXO from tx2 should be present and belong to Alice
    tx2_id = tx2.get_tx_id()
    assert (tx2_id, 0) in bc.utxo_pool
    assert bc.utxo_pool[(tx2_id, 0)].recipient == hash_alice
    assert bc.utxo_pool[(tx2_id, 0)].value == 50


def test_mining_and_chain_sync_between_nodes(setup_blockchain):
    # Setup blockchain and keys
    bc, sk_alice, pub_alice, priv_alice, hash_alice, _, _, _, hash_bob = setup_blockchain

    # --- Simulate node1 owning that blockchain ---
    node1 = CoreNode('localhost', 11001)
    node2 = CoreNode('localhost', 11002)

    # Give node1 the prepared blockchain
    node1.blcok_chain = bc

    wait()

    # First transaction: Spend UTXO tx0
    inp1 = TxInput("tx0", 0, pub_alice)
    out1 = TxOutput(50, hash_bob)
    tx1 = Transaction([inp1], [out1])
    tx1.sign_all_inputs([priv_alice])

    block1 = Block(0, [tx1], time.time(), "0" * 64)
    block1.Merkle_tree_creation()
    node1.blcok_chain.mine_block(block1)

    # Second transaction: Spend output from tx1 (simulate txid with block1 hash)
    inp2 = TxInput(block1.block_hash(), 0, pub_alice)
    out2 = TxOutput(50, hash_bob)
    tx2 = Transaction([inp2], [out2])
    tx2.sign_all_inputs([priv_alice])

    block2 = Block(1, [tx2], time.time(), block1.block_hash())
    block2.Merkle_tree_creation()
    node1.blcok_chain.mine_block(block2)

    # --- Simulate node2 syncing from node1 ---
    sock = node2.connect_to_peer(11001)
    node2.send_and_receive_message_to_peer(sock, (b"get_chain", None))

    time.sleep(1.0)  # Let async threads process

    # --- Assertions: node2 should now have same chain as node1 ---
    assert node2.blcok_chain.chain_validation()
    assert len(node2.blcok_chain.chain) == len(node1.blcok_chain.chain)
    assert node2.blcok_chain.chain[0].block_hash() == node1.blcok_chain.chain[0].block_hash()
    assert node2.blcok_chain.chain[1].block_hash() == node1.blcok_chain.chain[1].block_hash()


    
def test_mining_and_chain_sync_via_bootstrapper(setup_blockchain):
    # Setup blockchain and keys
    bc, sk_alice, pub_alice, priv_alice, hash_alice, _, _, _, hash_bob = setup_blockchain

    # --- Step 1: Start bootstrapper node ---
    bootstrapper = BootstrapperNode('localhost', 11000)

    # --- Step 2: Start node1 and register with bootstrapper ---
    node1 = CoreNode('localhost', 11001)
    node1.blcok_chain = bc

    wait()

    sock1 = node1.connect_to_peer(11000)
    node1.send_and_receive_message_to_peer(sock1, (b"registration", (node1.host, node1.port)))

    wait()

    # --- Step 3: Start node2 and get peers from bootstrapper ---
    node2 = CoreNode('localhost', 11002)

    sock2 = node2.connect_to_peer(11000)
    node2.send_and_receive_message_to_peer(sock2, (b"get_peers", None))

    wait()

    # --- Step 4: node1 mines a couple of blocks ---
    inp1 = TxInput("tx0", 0, pub_alice)
    out1 = TxOutput(50, hash_bob)
    tx1 = Transaction([inp1], [out1])
    tx1.sign_all_inputs([priv_alice])

    block1 = Block(0, [tx1], time.time(), "0" * 64)
    block1.Merkle_tree_creation()
    node1.blcok_chain.mine_block(block1)

    inp2 = TxInput(block1.block_hash(), 0, pub_alice)
    out2 = TxOutput(50, hash_bob)
    tx2 = Transaction([inp2], [out2])
    tx2.sign_all_inputs([priv_alice])

    block2 = Block(1, [tx2], time.time(), block1.block_hash())
    block2.Merkle_tree_creation()
    node1.blcok_chain.mine_block(block2)

    wait()

    # --- Step 5: node2 connects to node1 and requests the chain ---
    peer_host, peer_port = list(node2.peers)[0]  # Should be node1
    sock3 = node2.connect_to_peer(peer_port)
    node2.send_and_receive_message_to_peer(sock3, (b"get_chain", None))

    time.sleep(1.0)

    # --- Final Assertions ---
    assert node2.blcok_chain.chain_validation()
    assert len(node2.blcok_chain.chain) == len(node1.blcok_chain.chain)
    assert node2.blcok_chain.chain[0].block_hash() == node1.blcok_chain.chain[0].block_hash()
    assert node2.blcok_chain.chain[1].block_hash() == node1.blcok_chain.chain[1].block_hash()


def test_transaction_propagation_between_nodes(setup_blockchain):
    bc, sk_alice, pub_alice, priv_alice, hash_alice, _, _, _, hash_bob = setup_blockchain
    # Step 1: Setup two nodes
    node1 = CoreNode('localhost', 12001)
    node2 = CoreNode('localhost', 12002)
    node1.blcok_chain = bc  # node1 has UTXO pool with tx0 and tx1
    node2.blcok_chain = bc
    wait()
    # Step 3: Create a valid transaction on node1
    inp1 = TxInput("tx0", 0, pub_alice)
    out1 = TxOutput(150, hash_bob)
    tx = Transaction([inp1], [out1])
    tx.sign_all_inputs([priv_alice])
    # Step 4: node1 sends transaction to node2
    sock_tx = node1.connect_to_peer(12002)
    node1.send_message_to_peer(sock_tx, (b"transaction", tx))
    time.sleep(1.0)  # Let thread process
    # Step 5: Assert tx reached node2 and was accepted
    assert len(node2.blcok_chain.transaction_pool) == 0



def test_miner_pipeline_with_transaction_pool(setup_blockchain):
    bc, sk_alice, pub_alice, priv_alice, hash_alice, _, _, _, hash_bob = setup_blockchain

    # --- Setup genesis block ---
    genesis = Block(0, [], time.time(), "0" * 64)
    genesis.Merkle_tree_creation()
    bc.mine_block(genesis)

    # --- Create a transaction and add it to the pool ---
    inp = TxInput("tx0", 0, pub_alice)
    out = TxOutput(50, hash_bob)
    tx = Transaction([inp], [out])
    tx.sign_all_inputs([priv_alice])

    assert bc.validate_transaction(tx)

    bc.transaction_pool.add(tx)
    assert tx in bc.transaction_pool

    # --- Create candidate block from pool ---
    candidate_block = bc.create_candidate_block()
    assert tx in candidate_block.transactions

    # --- Validate candidate block before mining ---
    assert bc.block_validation(candidate_block)

    # --- Mine the block ---
    bc.mine_block(candidate_block)

    # --- Update UTXO pool and transaction pool ---
    bc.update_utxo_pool(candidate_block)
    bc.uptade_transaction_pool(candidate_block)
    bc.uptade_chain(candidate_block)

    # --- Final assertions ---
    assert len(bc.chain) == 2
    assert bc.chain_validation()

    tx_id = tx.get_tx_id()
    assert (tx_id, 0) in bc.utxo_pool
    assert bc.utxo_pool[(tx_id, 0)].recipient == hash_bob
    assert bc.utxo_pool[(tx_id, 0)].value == 50
    assert tx not in bc.transaction_pool

def test_miner_blocking_and_unblocking(setup_blockchain):
    # Unpack setup
    bc, sk_alice, pub_alice, priv_alice, hash_alice, _, _, _, hash_bob = setup_blockchain

    # Create genesis block and mine it
    genesis = Block(0, [], time.time(), "0" * 64)
    genesis.Merkle_tree_creation()
    bc.mine_block(genesis)
    bc.chain.append(genesis)  # Make sure genesis is in chain

    # Create first transaction and add to pool
    inp = TxInput("tx0", 0, pub_alice)
    out = TxOutput(50, hash_bob)
    tx1 = Transaction([inp], [out])
    tx1.sign_all_inputs([priv_alice])
    bc.transaction_pool.add(tx1)

    # Create MinerNode with this blockchain
    miner = MinerNode("127.0.0.1", 8000, chain=bc)

    # Wait a moment to ensure miner thread started and is waiting
    time.sleep(0.5)
    # Miner event should NOT be set since only 1 transaction in pool
    assert not miner.stat_mining_event.is_set(), "Miner event should be clear with only 1 tx"

    # Miner jobs queue should be empty (no mining job submitted)
    assert miner.jobs.empty(), "Jobs queue should be empty before second tx"

    # Add second transaction under lock and set event manually to simulate get_transaction
    inp2 = TxInput("tx1", 0, pub_alice)
    out2 = TxOutput(60, hash_bob)
    tx2 = Transaction([inp2], [out2])
    tx2.sign_all_inputs([priv_alice])

    with miner.chain_lock:
        miner.blcok_chain.transaction_pool.add(tx2)

    # Now simulate miner getting notified by calling set()
    miner.stat_mining_event.set()

    # # Wait shortly for miner thread to wake and submit mining job
    time.sleep(5)
    with miner.chain_lock:
        assert len(miner.blcok_chain.transaction_pool) == 0
    # # Now event should be cleared (miner clears it after submitting)
    assert not miner.stat_mining_event.is_set(), "Miner event should be cleared after mining job submission"



def test_miner_propagates_blocks_to_all_nodes(setup_blockchain_for_mining):
    bc, sk_alice, pub_alice, priv_alice, hash_alice, sk_bob, pub_bob, priv_bob, hash_bob = setup_blockchain_for_mining
    # Step 4: Start BootstrapperNode
    bootstrapper = BootstrapperNode('localhost', 13000)
    wait()
    # Step 5: Start 3 CoreNodes with same blockchain
    nodes = []
    for i in range(3):
        node = CoreNode('localhost', 13001 + i)
        node.blcok_chain = copy.deepcopy(bc)
        wait()

        # Register node with bootstrapper
        sock = node.connect_to_peer(13000)
        node.send_message_to_peer(sock, (b"registration", (node.host, node.port)))
        nodes.append(node)

    # Step 6: Start MinerNode with same blockchain and register with bootstrapper
    miner = MinerNode('localhost', 13010, chain=copy.deepcopy(bc))
    sock = miner.connect_to_peer(13000)
    miner.send_message_to_peer(sock, (b"registration", (miner.host, miner.port)))

    # Step 7: Wait to ensure everyone discovers each other
    wait()
    for node in nodes:
        sock = node.connect_to_peer(13000)
        node.send_and_receive_message_to_peer(sock, (b"get_peers", None))

    wait()
    sock = miner.connect_to_peer(13000)
    miner.send_and_receive_message_to_peer(sock, (b"get_peers", None))

    wait()

    # Step 8: Trigger mining
    miner.stat_mining_event.set()

    # Step 9: Wait for miner to mine both blocks
    time.sleep(10)

    # Step 10: Wait for blocks to propagate

    # assert miner.blcok_chain.chain_validation()

    # Step 11: Assertions
    chain_hashes = [b.block_hash() for b in miner.blcok_chain.chain]
    for node in nodes:
        assert node.blcok_chain.chain_validation()
        assert len(node.blcok_chain.chain) == len(miner.blcok_chain.chain)
        for i, block in enumerate(node.blcok_chain.chain):
            assert block.block_hash() == chain_hashes[i]

        # After all previous assertions, create a new tx from Alice to Bob
    tx_input = TxInput("tx0", 0, hash_bob)  # Spend from utxo tx0, index 0
    tx_output = TxOutput(50, hash_alice)
    new_tx = Transaction([tx_input], [tx_output])
    new_tx.sign_all_inputs([priv_alice])

    # Broadcast transaction to all CoreNodes
    for node in nodes:
        sock = node.connect_to_peer(node.port)  # Connect to each node
        miner.send_message_to_peer(sock, (b"transaction", new_tx))
        sock.close()

    time.sleep(5)

    # Check if each core node has received and added the transaction to their pool
    for node in nodes:
        print(node.logs , "\n")



def test_two_miners_fork_detection(setup_blockchain_for_mining):
    bc, sk_alice, pub_alice, priv_alice, hash_alice, sk_bob, pub_bob, priv_bob, hash_bob = setup_blockchain_for_mining
    # Start BootstrapperNode
    bootstrapper = BootstrapperNode('localhost', 13000)
    wait()
    # Start 3 CoreNodes with the same blockchain
    nodes = []
    for i in range(5):
        node = CoreNode('localhost', 13001 + i)
        node.blcok_chain = copy.deepcopy(bc)
        wait()
        sock = node.connect_to_peer(13000)
        node.send_message_to_peer(sock, (b"registration", (node.host, node.port)))
        nodes.append(node)

    # Start Miner 1
    miner1 = MinerNode('localhost', 13010, chain=copy.deepcopy(bc))
    sock = miner1.connect_to_peer(13000)
    miner1.send_message_to_peer(sock, (b"registration", (miner1.host, miner1.port)))

    # Start Miner 2 (another independent miner)
    miner2 = MinerNode('localhost', 13011, chain=copy.deepcopy(bc))
    sock = miner2.connect_to_peer(13000)
    miner2.send_message_to_peer(sock, (b"registration", (miner2.host, miner2.port)))

    miner3 = MinerNode('localhost', 13012, chain=copy.deepcopy(bc))
    sock = miner3.connect_to_peer(13000)
    miner3.send_message_to_peer(sock, (b"registration", (miner3.host, miner3.port)))

    # Discover peers
    wait()
    for node in nodes:
        sock = node.connect_to_peer(13000)
        node.send_and_receive_message_to_peer(sock, (b"get_peers", None))

    for miner in [miner1, miner2 , miner3]:
        sock = miner.connect_to_peer(13000)
        miner.send_and_receive_message_to_peer(sock, (b"get_peers", None))

    wait()
    # Trigger mining on both miners at the same time
    miner1.stat_mining_event.set()
    miner2.stat_mining_event.set()
    miner3.stat_mining_event.set()
    # Let them mine concurrently, possibly leading to a fork
    time.sleep(45)

    # Optional: Check how CoreNodes reacted
    for node in [miner1, miner2 , miner3]:
        print(f"\nNode {node.port} chain:")
        for block in node.blcok_chain.chain:
            print(block.block_hash())

   
    # Optional: Check if any node resolved the fork (e.g., by chain length or received blocks)
    # You can also try to trigger chain replacement by broadcasting the longer chain