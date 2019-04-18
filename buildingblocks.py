import sys
import os

# represents a transaction
class Transaction:
    def __init__(self, number, inp, out, sig):
        self.number = number
        self.inp = inp
        self.out = out
        self.sig = sig

# represents a block, contains a single transaction for simplicity
# each block references a prev block, has an isGenesis flag,
# and a flag indicating if the internal transaction is a mergesplit fee
class Block:
    def __init__(self, tx, prev, isGenesis=False, isFee=False, isSplit=False, isMerge=False):
        self.tx = tx
        self.prev = prev
        self.isGenesis = isGenesis
        self.isFee = isFee
        self.isSplit = isSplit
        self.isMerge = isMerge

# represents each BlockNode in the BlockChain
class BlockNode:
    def __init__(self, block=None, prev=None):
        self.block = block
        self.prev = prev