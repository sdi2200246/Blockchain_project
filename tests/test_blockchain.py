# BlockChain logic — pure, fast
import pytest
from blockchain import BlockChain
from block import Block
from exceptions import BlockchainError, InvalidBlockError
from conftest import make_tx
import time


class TestValidateTransaction:
    def test_valid_tx_passes(self, chain_with_utxos, alice, bob):
        tx = make_tx(alice, bob, 50, "tx0", 0)
        assert chain_with_utxos.validate_transaction(tx) is True

    def test_missing_utxo_raises(self, chain_with_utxos, alice, bob):
        tx = make_tx(alice, bob, 50, "tx_doesnt_exist", 0)
        with pytest.raises(BlockchainError, match="UTXO"):
            chain_with_utxos.validate_transaction(tx)

    def test_wrong_pubkey_raises(self, chain_with_utxos, alice, bob):
        # bob tries to spend alice's UTXO
        tx = make_tx(bob, bob, 50, "tx0", 0)
        with pytest.raises(BlockchainError, match="pubkey"):
            chain_with_utxos.validate_transaction(tx)

    def test_double_spend_in_same_tx_raises(self, chain_with_utxos, alice, bob):
        from transactions import TxInput, TxOutput, Transaction
        inp1 = TxInput("tx0", 0, alice["pub"])
        inp2 = TxInput("tx0", 0, alice["pub"])  # same input twice
        out = TxOutput(50, bob["hash"])
        tx = Transaction([inp1, inp2], [out])
        tx.sign_all_inputs([alice["priv"], alice["priv"]])
        with pytest.raises(BlockchainError, match="doublespen"):
            chain_with_utxos.validate_transaction(tx)

    def test_insufficient_funds_raises(self, chain_with_utxos, alice, bob):
        tx = make_tx(alice, bob, 9999, "tx0", 0)  # only 50 in the UTXO
        with pytest.raises(BlockchainError, match="fundings"):
            chain_with_utxos.validate_transaction(tx)


class TestMining:
    def test_mine_block_finds_valid_nonce(self, chain_with_genesis):
        # mine_block sets nonce so hash meets difficulty
        block = Block(1, [], time.time(), chain_with_genesis.get_last_block().block_hash())
        chain_with_genesis.mine_block(block)
        assert block.block_hash().startswith(chain_with_genesis.difficulty)

    def test_mine_block_does_not_append_to_chain(self, chain_with_genesis):
        """Documents that mine_block is pure PoW, not chain mutation."""
        before = len(chain_with_genesis.chain)
        block = Block(1, [], time.time(), chain_with_genesis.get_last_block().block_hash())
        chain_with_genesis.mine_block(block)
        assert len(chain_with_genesis.chain) == before

    def test_full_mining_flow(self, chain_with_genesis, alice, bob):
        """Mine + append + update UTXO, as the node does it."""
        tx = make_tx(alice, bob, 50, "tx0", 0)
        chain_with_genesis.transaction_pool.add(tx)

        # Need 2+ txs for create_candidate_block, so make another
        tx2 = make_tx(alice, bob, 50, "tx1", 0)
        chain_with_genesis.transaction_pool.add(tx2)

        candidate = chain_with_genesis.create_candidate_block()
        chain_with_genesis.mine_block(candidate)
        chain_with_genesis.update_utxo_pool(candidate)
        chain_with_genesis.uptade_transaction_pool(candidate)
        chain_with_genesis.uptade_chain(candidate)

        assert len(chain_with_genesis.chain) == 2
        assert chain_with_genesis.chain_validation()
        assert tx not in chain_with_genesis.transaction_pool


class TestBlockValidation:
    def test_valid_block_passes(self, chain_with_genesis, alice, bob):
        tx = make_tx(alice, bob, 50, "tx0", 0)
        prev = chain_with_genesis.get_last_block()
        block = Block(1, [tx], time.time(), prev.block_hash())
        chain_with_genesis.mine_block(block)
        assert chain_with_genesis.block_validation(block, set()) is True

    def test_unmined_block_fails_difficulty(self, chain_with_genesis, alice, bob):
        tx = make_tx(alice, bob, 50, "tx0", 0)
        prev = chain_with_genesis.get_last_block()
        block = Block(1, [tx], time.time(), prev.block_hash(), nonce=0)
        # not mined — almost certainly doesn't hit difficulty
        with pytest.raises(BlockchainError, match="difficulty"):
            chain_with_genesis.block_validation(block, set())

    def test_wrong_previous_hash_fails(self, chain_with_genesis, alice, bob):
        tx = make_tx(alice, bob, 50, "tx0", 0)
        block = Block(1, [tx], time.time(), "deadbeef" * 8)
        chain_with_genesis.mine_block(block)
        with pytest.raises(InvalidBlockError, match="wrong link"):
            chain_with_genesis.block_validation(block, set())

    def test_seen_block_rejected(self, chain_with_genesis, alice, bob):
        tx = make_tx(alice, bob, 50, "tx0", 0)
        prev = chain_with_genesis.get_last_block()
        block = Block(1, [tx], time.time(), prev.block_hash())
        chain_with_genesis.mine_block(block)
        seen = {block.block_hash()}
        with pytest.raises(BlockchainError, match="seen"):
            chain_with_genesis.block_validation(block, seen)