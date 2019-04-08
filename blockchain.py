import sys
import os
import copy
import json
import numbers
from hashlib import sha256 as H
import random
from collections import defaultdict
from threading import Thread
import time
import nacl.encoding
import nacl.signing
from threading import Lock
from apscheduler.scheduler import Scheduler
from .blockchain import BlockChain
from .utils import Utils
from .node import Node
from .community import Community
from .network import Network


# blockchain data structure
class BlockChain:
    
    def __init__(self):
        self.chains = []
        self.blockToIndex = {}
        self.blockToNode = {}
        self.longestIndex = 0
        self.longestLength = 0
        self.parents = defaultdict(int)
        
    # adds a genesis block to the blockchain
    def setGenesis(self, genesis):
        front = BlockNode(genesis)
        genesisSerialized = H(str.encode(Utils.serializeBlock(genesis))).hexdigest()
        self.blockToNode[genesisSerialized] = front
        self.blockToIndex[genesisSerialized] = 0
        self.longestLength = 1
        self.chains.append(front)
    
    # adds a block to the blockchain
    # handles forking if block added as new branch from previously seen block
    def addBlock(self, block):
        # constructs a new BlockNode
        node = BlockNode(block, self.blockToNode[block.prev])
        serialized = H(str.encode(Utils.serializeBlock(block))).hexdigest()
        self.blockToNode[serialized] = node
        if self.parents[block.prev] >= 1:
            # represents a fork
            self.chains.append(node)
            self.blockToIndex[serialized] = len(self.chains)-1
        else:
            # extends an existing chain
            self.chains[self.blockToIndex[block.prev]] = node
            self.blockToIndex[serialized] = self.blockToIndex[block.prev]
        self.parents[block.prev] += 1
        current, size = node, 0
        while current:
            current = current.prev
            size += 1
        if size > self.longestLength:
            # update the longest length and the index of the longest chain
            self.longestLength = size
            self.longestIndex = self.blockToIndex[serialized]
    
    # returns pointer to tail of the longest chain
    def longestChain(self):
        return self.chains[self.longestIndex]

    def lengthOfLongestChain(self):
        current, size = self.longestChain(), 0
        while current:
            current = current.prev
            size += 1
        return size
    
    # checks that a block we want to add has its prev hash pointing to a block that exists
    def isValidPrev(self, prev):
        return prev in self.blockToNode and prev in self.blockToIndex

    # logs node's blockchain to a file
    def log(self, filename=None):
        current = self.longestChain()
        output = []
        while current:
            d = {"tx": H(str.encode(current.block.tx)).hexdigest(), "prev": current.block.prev}
            dict(sorted(d.items()))
            output.append(d)
            current = current.prev
        if filename:
            with open(filename, 'w') as outfile:
                json.dump(output, outfile, sort_keys=False, indent=4, ensure_ascii=False)
        return output