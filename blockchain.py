import hashlib
import json
import time
import ecdsa
from transactions import Transaction ,TxOutput, TxInput
from block import Block
from exceptions import BlockchainError, InvalidBlockError


def hash_pubkey(pubkey_hex):
    return hashlib.sha256(bytes.fromhex(pubkey_hex)).hexdigest()

class BlockChain:
    def __init__(self , difficulty="0000"):
        self.difficulty = difficulty
        self.chain: list[Block] = []
        self.transaction_pool: set[Transaction] = set()
        self.utxo_pool: dict[tuple[str, int], TxOutput] = {} #str:prev_txid int:output_index

 
    def get_last_block(self):

        if not self.chain:
            return None

        return self.chain[len(self.chain)-1]


    def uptade_transaction_pool(self , block:Block):
        for tx in block.transactions:
            self.transaction_pool.discard(tx)

    def uptade_chain(self , block:Block):
         self.chain.append(block)


    def update_utxo_pool(self , block:Block):
       for tx in block.transactions:
        # Remove spent UTXOs
        for tx_in in tx.inputs:
            utxo_key = (tx_in.prev_txid, tx_in.output_index)
            self.utxo_pool.pop(utxo_key, None)  # pop safely, no error if missing

        # Add new UTXOs
        tx_id = tx.get_tx_id()
        for index, tx_out in enumerate(tx.outputs):
            utxo_key = (tx_id, index)
            self.utxo_pool[utxo_key] = tx_out


    def mine_block(self , block:Block):
        nonce = 0
        while True:
            block.nonce = nonce
            b_hash = block.block_hash()
            if b_hash[:len(self.difficulty)] == self.difficulty:
                break
            nonce+=1

        return


    def validate_transaction(self , tx:Transaction):
        input_total = 0
        output_total = sum(out.value for out in tx.outputs)
        seen_inputs = set()

        for tx_input in tx.inputs:
            key = (tx_input.prev_txid, tx_input.output_index)

            # Check UTXO exists
            utxo = self.utxo_pool.get(key)
            if not utxo:
                raise BlockchainError("Error:[validate_transaction()][UTXO_doesn't exist]")
               

            # Check pubkey hash matches recipient of UTXO
            if hash_pubkey(tx_input.pubkey) != utxo.recipient:
                raise BlockchainError("Error:[validate_transaction()][pubkey_missmuch detected]")

            # Prevent double spending in the same tx
            if key in seen_inputs:
                raise BlockchainError("Error:[validate_transaction()][doublespennding detected]")
            seen_inputs.add(key)

            input_total += utxo.value

        # Verify that input covers output
        if input_total < output_total:
            raise BlockchainError("Error:[validate_transaction()][not enough fundings detected]")
            

        # Verify digital signatures
        if not tx.verify_all_signatures():
            raise BlockchainError("Error:[validate_transaction()][wrong signuture detected]")
        
        return True

    ## Not fully ready
    def chain_validation(self , old_chain = None):

        if not self.chain:
            raise BlockchainError("Error:[chain_validation()][empty chain detected]")
        

        if old_chain and len(old_chain.chain) >= len(self.chain):
            raise BlockchainError("Error:[chain_validation()][old chain received]")


        b_hash = self.chain[0].block_hash()

        for i , block  in enumerate(self.chain[1:] , start=1):
            temp_block = Block(i, block.transactions , block.timestamp , b_hash , block.nonce , block.merkle_tree)
            temp_hash =  temp_block.block_hash()


            if temp_hash != block.block_hash():
               raise BlockchainError("Error:[chain_validation()][wrong link detected]")
            
            b_hash = temp_hash

        return True

    def block_validation(self , block:Block , seen:set[Block]):

        hash = block.block_hash()
        if hash in seen:
            raise BlockchainError("Error:[block_validation()][seen block detected]")            
        
        seen.add(hash)

        if block.previous_hash != self.get_last_block().block_hash():
            raise InvalidBlockError("Error:[block_validation()][wrong link detected]")
        
        if block.block_hash()[:len(self.difficulty)] != self.difficulty:
            raise BlockchainError("Error:[block_validation()][difficulty test failed]")
        
        
        for tx in block.transactions:
            if not self.validate_transaction(tx):
                raise BlockchainError("Error:[block_validation()][invalid trasnaction detected]")
        
        return True

    def create_candidate_block(self):
    
        selected_txs = list(self.transaction_pool)[:2]
        last_block = self.get_last_block()

        if last_block == None:
            raise BlockchainError("Error:[create_candidate_block][empty chain detected]")

        block = Block(last_block.index+1 , selected_txs , time.time() , last_block.block_hash())
        return block


     # ... your existing __init__ ...

    def print_pools_state(self):
        print("----- Transaction Pool -----")
        if not self.transaction_pool:
            print("Transaction pool is empty.")
        else:
            for i, tx in enumerate(self.transaction_pool):
                print(f"Transaction {i}: {tx}")

        print("\n----- UTXO Pool -----")
        if not self.utxo_pool:
            print("UTXO pool is empty.")
        else:
            for (txid, index), tx_output in self.utxo_pool.items():
                print(f"UTXO: txid={txid}, index={index}, output={tx_output}")

        print("-------------------------")
