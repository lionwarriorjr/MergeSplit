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
import blockchain
import utils
import node
import network
import buildingblocks


# represents an individual network/subgroup of nodes/transaction pools
class Community:
    
    def __init__(self, network, id, pool, keys=None, nodeList=None):
        # store parent network this community is a part of
        self.network = network
        # number of nodes/forgers in community
        self.nodeCount = 0
        # stores the forgers
        self.nodes = []
        # quick lookup for nodes based on public key address
        self.nodeLookup = {}
        # community's unique transaction pool
        self.pool = pool
        # community's unique id
        self.id = id
        if nodeList != None:
            self.nodeCount = len(nodeList)
            self.nodes = nodeList
            for i in range(self.nodeCount):
                self.nodeLookup[node.getPublicKey] = nodes[i]
        else:
            # create constituent nodes of community
            self.nodeCount = len(keys)
            for i in range(self.nodeCount):
                node = node.Node(keys[i][0], keys[i][1], self)
                self.nodes.append(node)
                self.nodeLookup[keys[i][0]] = node

    def getCommunityNodes(self):
        return self.nodes
    
    def getCommunityId(self):
        return self.id

    # check if a public key address is used in this community
    def contains(self, address):
        for n in self.nodes:
            if n.publicKey == address:
                return True
        return False

    # fetch up-to-date blockchain for new nodes/forgers when added to community
    def fetchUpToDateBlockchain(self):
        if self.nodeCount > 0:
            blockchain = self.nodes[0].chain
            # return deep copy of a node's blockchain
            return copy.deepcopy(blockchain)
        else:
            return BlockChain()

    # dynamically add forgers to the community
    def add(self, publicKey, privateKey):
        # create the node
        node = node.Node(publicKey, privateKey, self)
        self.nodes.append(node)
        self.nodeLookup[publicKey] = node
        # update node count
        self.nodeCount += 1
        node.chain = self.fetchUpToDateBlockchain()
        # start sending asynchronous merge/split proposals
        node.setRequestTimeout()

    def selectCreator(self):
        # randomly sample validators from nodeCount according to stake
        dist = [0] * self.nodeCount
        totalStake = sum([node.stake for node in self.nodes])
        dist = [node.stake / totalStake for node in self.nodes]
        # randomly samply validator for proof of stake
        creator = np.random.choice(self.nodeCount, 1, p=dist)
        return self.nodes[creator]

    # updates stake for a node in the community
    def updateStake(self, transaction):
        stakes = defaultdict(int)
        for inp in transaction.inp:
            if inp['output']['pubkey'] in self.nodeLookup:
                stakes[inp['output']['pubkey']] -= inp['output']['value']
        for out in transaction.out:
            if out['pubkey'] in self.nodeLookup:
                stakes[out['pubkey']] += out['value']
        for node in stakes:
            self.nodeLookup[node].stake += stakes[node]

    # driver run function executed within thread context
    def run(self):
        # as long as valid transactions exist in the community
        while self.validTransactionExists():
            # randomly sample a validator to propose a block
            creator = self.selectCreator()
            for transaction in self.pool:
                # select a transaction to include in the proposed block
                tx = utils.Utils.serializeTransaction(transaction)
                # validate the transaction
                if creator.validate(transaction, creator.chain.longestChain()):
                    prev = H(str.encode(utils.Utils.serializeBlock(self.fetchUpToDateBlockchain.longestChain().block))).hexdigest()
                    block = buildingblocks.Block(tx, prev)
                    # broadcast block to be added to the blockchain
                    self.broadcast(block)

    # construct mergesplit transaction fee (novel incentive scheme)
    def accrueTransactionFee(self, receiver):
        inp = []
        out = [{"value": self.network.mergesplitFee, "pubkey": receiver.address}]
        serializedInput = "".join([str(inp['number']) + str(inp['output']['value']) + str(inp['output']['pubkey'])
                                for inp in receiverInput])
        serializedOutput = "".join([str(out['value']) + str(out['pubkey']) for out in receiverOutput])
        # message to sign for mergesplit fee
        message = str.encode(serializedInput + serializedOutput)
        # sign the message
        signed = receiver.prikey.sign(message, encoder=nacl.encoding.HexEncoder)
        sig = str(signed.signature, 'utf-8')
        number = H(str.encode(serializedInput + serializedOutput + sig)).hexdigest()
        # construct mergesplit transaction
        transaction = buildingblocks.Transaction(number, receiverInput, receiverOutput, sig)
        tx = utils.Utils.serializeTransaction(transaction)
        prev = H(str.encode(utils.Utils.serializeBlock(self.fetchUpToDateBlockchain.longestChain().block))).hexdigest()
        block = buildingblocks.Block(tx, prev, False, True)
        # add mergesplit fee block to every node's chain
        for node in self.nodes:
            node.chain.addBlock(block)
        # update stake of receiver of the fee
        receiver.stake += self.network.mergesplitFee
        return True

    # broadcasts a proposed block to all nodes to verify and add to their blockchains
    def broadcast(self, block):
        # each node verifies the block
        for node in self.nodes:
            if not node.verifyProposal(block):
                return False
        # if verification passed, nodes add the block to their blockchain
        for node in self.nodes:
            # restart indicates that each node should stop their pow calculation
            node.chain.addBlock(block)
        # update stakes of forgers after processing transaction
        self.updateStake(transaction)
        return True

    ### TODO: implement merging functionality
    def merge(self, neighbor):
        # Query all nodes in both community to see if they want to merge
        neighborNodes = neighbor.getCommunityNodes
        for node in neighborNodes:
            if not node.approveMerge():
                return False

        for node in self.nodes:
            if not node.approveMerge():
                return False
        
        newCommunity = None
        # update blockchain for all nodes in both communities, inserting a mergeblock between the two chains
        # combine the two communities transaction pool together

        newCommunity = None

        return (True, newCommunity)
    
    def split(self):
        # randomly select half the nodes to split
        newCommunityNodes = []
        shuffle(self.nodes)
        for i in range(int(self.nodeCount/2)):
            newCommunityNodes.append(self.nodes[i])
        
        # Query all nodes in both community to see if they want to split
        for node in self.nodes:
            if not node.approveSplit():
                return False

        for newNode in newCommunityNodes:
            self.nodes.remove(newNode)

        # add a new split block to remaining nodes blockchain
        #TODO generate transaction that drains money from nodes splitting
        transaction = None
        serial = utils.Utils.serializeBlock(self.fetchUpToDateBlockchain.longestChain().block)
        splitBlock = buildingblocks.Block(transaction, H(str.encode(serial)).hexdigest(), isSplit=True)
        for node in self.nodes:
            node.chain.addBlock(splitBlock)

        # create a new blockchain for all nodes that are in the new community
        #TODO generate transaction granting money to nodes in new community
        newTransaction = None 
        newBlock = buildingblocks.Block(newTransaction, None)
        newBlockChain = blockchain.BlockChain()
        newBlockChain.setGenesis(newBlock)
        for node in newCommunityNodes:
            node.setBlockChain(newBlockChain)

        community1 = community.Community(self.network, random.randint(0,10**10), 
                                         pool=self.pool, keys=None, nodeList=self.nodes)
        community2 = community.Community(self.network, random.randint(0,10**10), 
                                         pool=[], keys=None, nodeList=newCommunityNodes)
        return (True, community1, community2)

    # quick check to find length of longest chain in each node's blockchain in a community
    # returns the length of this longest chain if all nodes share the same longest chain
    # returns False if there are 2 forked chains in a community with same longest length (can just rerun)
    def checkForMatchedSequences(self):
        for i in range(0,len(self.nodes)-1):
            current = self.nodes[i].chain.longestChain()
            nxt = self.nodes[i+1].chain.longestChain()
            size = 0
            while current:
                if (current.block.tx != nxt.block.tx
                    or current.block.prev != nxt.block.prev):
                    return False
                current = current.prev
                nxt = nxt.prev
                size += 1
            if nxt:
                return False
        return size