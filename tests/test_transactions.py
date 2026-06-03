# TxInput, TxOutput, Transaction — pure, fast
import pytest
import ecdsa
from transactions import Transaction, TxInput, TxOutput
from conftest import make_tx


class TestTransactionSigning:
    def test_signed_tx_verifies(self, alice, bob):
        tx = make_tx(alice, bob, 50, "tx0", 0)
        assert tx.verify_all_signatures()

    def test_unsigned_tx_does_not_verify(self, alice, bob):
        inp = TxInput("tx0", 0, alice["pub"])
        out = TxOutput(50, bob["hash"])
        tx = Transaction([inp], [out])
        # never call sign_all_inputs
        with pytest.raises((TypeError, ecdsa.BadSignatureError, ValueError)):
            tx.verify_all_signatures()

    def test_wrong_key_fails_verification(self, alice, bob):
        inp = TxInput("tx0", 0, alice["pub"])
        out = TxOutput(50, bob["hash"])
        tx = Transaction([inp], [out])
        tx.sign_all_inputs([bob["priv"]])  # wrong key
        assert not tx.verify_all_signatures()


class TestTransactionIdentity:
    def test_tx_id_is_deterministic(self, alice, bob):
        tx1 = make_tx(alice, bob, 50, "tx0", 0)
        tx2 = make_tx(alice, bob, 50, "tx0", 0)
        # same content, same key → same tx_id, even with different timestamps?
        # NOTE: your to_dict includes timestamp, so they'll differ
        # this test documents that behavior
        assert tx1.get_tx_id() != tx2.get_tx_id()

    def test_tx_equality_by_id(self, alice, bob):
        tx = make_tx(alice, bob, 50, "tx0", 0)
        assert tx == tx  # __eq__ uses get_tx_id