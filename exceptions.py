class BlockchainError(Exception):
    def __init__(self, message):
        super().__init__("BlockchainError:"+message)


class InvalidBlockError(BlockchainError):
    def __init__(self, message):
        super().__init__("InvalidBlockError:"+message)