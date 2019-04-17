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


# represents an individual network/subgroup of nodes/transaction pools
class Community:
    
    def __init__(self, network, keys=None, id, nodeList=None, pool=None):
        # store parent network this community is a part of
        self.network = network
        # number of nodes/forgers in community
        self.nodeCount = 0
        # stores the forgers
        self.nodes = []
        # quick lookup for nodes based on public key address
        self.nodeLookup = {}
        # community's unique transaction pool
        self.pool = pool or []
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
                node = Node(keys[i][0], keys[i][1], self)
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
        node = Node(publicKey, privateKey, self)
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
                tx = Utils.serializeTransaction(transaction)
                # validate the transaction
                if creator.validate(transaction, creator.chain.longestChain()):
                    prev = H(str.encode(Utils.serializeBlock(self.fetchUpToDateBlockchain.longestChain().block))).hexdigest()
                    block = Block(tx, prev)
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
        transaction = Transaction(number, receiverInput, receiverOutput, sig)
        tx = Utils.serializeTransaction(transaction)
        prev = H(str.encode(Utils.serializeBlock(self.fetchUpToDateBlockchain.longestChain().block))).hexdigest()
        block = Block(tx, prev, False, True)
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
        neighborNodes = neighbor.getCommunityNodes()
        for node in neighborNodes:
            if not node.approveMerge():
                return False

        for node in self.nodes:
            if not node.approveMerge():
                return False
        
        # update blockchain for all nodes in both communities, inserting a mergeblock between the two chains
        # combine the two communities transaction pool together
        mergeBlock = Block(None, self.nodes[self.nodeCount-1], isGenesis=False, isFee=False, isSplit=False, isMerge=True)
        newChain = self.nodes[0].chain# TODO: make this better than just making it 0th node - do by voting
        newChain.addBlock(mergeBlock)
        insertPoint = newChain.longestLength
        longestNeighbor = neighBorNodes[0].longestChain()#TODO: same as above
        lengthAdded = 1
        while !longestNeighbor.isGenesis:
            newChain.insert(insertPoint,longestNeighbor)
            lengthAdded = lengthAdded+1
        # now need to add genesis block to chain append
        # set neighbors genesis block to this block (currently won't work unless we change the hash sequence to not take prev)
        longestNeigbor.changePrev(mergeBlock)
        newChain.insert(insertPoint,longestNeighbor)
        newChain.longestLength = newChain.longestLength+lengthAdded + 1
        # proably can do better than looping over all nodes
        for node in self.nodews:
            node.chain = newChain
        ''' old pow stuff
        while True:
            nonce = 0
            blockHash = (H(mergeBlock.encode('utf-8') + nonce.encode('utf-8'))).hexdigest()
            if int(blockHash,16) <= int(H(neighbor.nodes[0].encode('utf-8')),16):
                # successful merge
                newChain = self.nodes[0].chain# TODO: make this better than just making it 0th node - do by voting
                newChain.addBlock(mergeBlock)
                insertPoint = newChain.longestLength
                longestNeighbor = neighBorNodes[0].longestChain()#TODO: same as above
                lengthAdded = 1
                while !longestNeighbor.isGenesis:
                    newChain.insert(insertPoint,longestNeighbor)
                    lengthAdded = lengthAdded+1
                # now need to add genesis block to chain append
                newChain.insert(insertPoint,longestNeighbor)
                newChain.longestLength = newChain.longestLength+lengthAdded + 1
                # proably can do better than looping over all nodes
                for node in self.nodews:
                    node.chain = newChain
                break
            else:
                nonce = nonce + 1'''
        for node in neighborNodes:
            node.chain = newChain
            self.nodes.append(node)
            self.nodeLookup[node.getPublicKey] = self.nodes[self.nodeCount]
            self.nodeCount = self.nodeCount+1
        #self.nodeCount = self.nodeCount+neighbor.nodeCount
        for tx in neighbor.pool:
            self.pool.append(tx)
        return (True, self)
    
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
        splitBlock = Block(transaction, H(str.encode(Utils.serializeBlock(self.fetchUpToDateBlockchain.longestChain().block))).hexdigest(), isSplit=True)
        for node in self.nodes:
            node.chain.addBlock(splitBlock)

        # create a new blockchain for all nodes that are in the new community
        #TODO generate transaction granting money to nodes in new community
        newTransaction = None 
        newBlock = Block(newTransaction, None)
        newBlockChain = BlockChain()
        newBlockChain.setGenesis(newBlock)
        for node in newCommunityNodes:
            node.setBlockChain(newBlockChain)

        community1 = Community(self.network, keys=None, random.randint(0,10**10), nodeList=self.nodes, pool=self.pool)
        community2 = Community(self.network, keys=None, random.randint(0,10**10), nodeList=newCommunityNodes)
        return (True, community1, community2)