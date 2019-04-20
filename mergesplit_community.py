import sys
import os
import copy
import json
import numpy as np
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
import mergesplit_node
import mergesplit_network
import buildingblocks


# implements an individual network/subgroup of nodes/transaction pools
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
                nodes = self.nodes
                self.nodeLookup[nodes[i].getPublicKey] = nodes[i]
        else:
            # create constituent nodes of community
            self.nodeCount = len(keys)
            for i in range(self.nodeCount):
                node = mergesplit_node.Node(keys[i][0], keys[i][1], self)
                self.nodes.append(node)
                self.nodeLookup[keys[i][0]] = node
        for node in self.nodes:
            node.setRequestTimeout()

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
            chain = self.nodes[0].chain
            # return deep copy of a node's blockchain
            return copy.deepcopy(chain)
        else:
            return blockchain.BlockChain()

    # dynamically add forgers to the community
    def add(self, publicKey, privateKey):
        # create the node
        node = mergesplit_node.Node(publicKey, privateKey, self)
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
        if totalStake == 0:
            dist = [1./len(self.nodes) for node in self.nodes]
        else:
            dist = [node.stake / totalStake for node in self.nodes]
        # randomly samply validator for proof of stake
        creator = np.random.choice(self.nodeCount, 1, p=dist)[0]
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

    # check if a transaction exists in pool that could be added to longest chain
    def validTransactionExists(self):
        for node in self.nodes:
            if node.validTransactionExists():
                return True
        return False

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
                    chain = self.nodes[0].chain
                    prev = H(str.encode(utils.Utils.serializeBlock(chain.longestChain().block))).hexdigest()
                    block = buildingblocks.Block(tx, prev)
                    # broadcast block to be added to the blockchain
                    self.broadcast(block)
                    break

    # construct mergesplit transaction fee (novel incentive scheme)
    def accrueTransactionFee(self, receiver):
        inp = []
        out = [{"value": mergesplit_network.Network.mergesplitFee, "pubkey": receiver.address}]
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
        chain = self.nodes[0].chain
        prev = H(str.encode(utils.Utils.serializeBlock(chain.longestChain().block))).hexdigest()
        block = buildingblocks.Block(tx, prev, False, True)
        # add mergesplit fee block to every node's chain
        for node in self.nodes:
            node.chain.addBlock(block)
        # update stake of receiver of the fee
        receiver.stake += mergesplit_network.Network.mergesplitFee
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
        self.updateStake(utils.Utils.deserializeTransaction(block.tx))
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
        mergeBlock = buildingblocks.Block(None, self.nodes[self.nodeCount-1], isGenesis=False, isFee=False, isSplit=False, isMerge=True)
        newChain = self.nodes[0].chain# TODO: make this better than just making it 0th node - do by voting
        newChain.addBlock(mergeBlock)
        insertPoint = newChain.longestLength
        longestNeighbor = neighborNodes[0].longestChain()#TODO: same as above
        lengthAdded = 1
        while not longestNeighbor.isGenesis:
            newChain.insert(insertPoint,longestNeighbor)
            lengthAdded = lengthAdded+1
        # now need to add genesis block to chain append
        # set neighbors genesis block to this block (currently won't work unless we change the hash sequence to not take prev)
        longestNeighbor.changePrev(mergeBlock)
        newChain.insert(insertPoint,longestNeighbor)
        newChain.longestLength = newChain.longestLength+lengthAdded + 1
        # proably can do better than looping over all nodes
        for node in self.nodews:
            node.chain = newChain
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
        np.random.shuffle(self.nodes)
        for i in range(int(self.nodeCount/2)):
            newCommunityNodes.append(self.nodes[i])
        
        # Query all nodes in both communities to see if they want to split
        approved = 0
        for node in self.nodes:
            if node.approveSplit():
                approved += 1
        if approved < self.nodeCount/2:
            return False

        pubkeys = []
        for newNode in newCommunityNodes:
            pubkeys.append(newNode.publicKey)
            self.nodes.remove(newNode)

        transaction, newTransaction = self.generateSplitTransactions(pubkeys)
        transaction = utils.Utils.serializeTransaction(transaction)
        newTransaction = utils.Utils.serializeTransaction(newTransaction)

        # add a new split block to remaining nodes blockchain
        serial = utils.Utils.serializeBlock(self.fetchUpToDateBlockchain().longestChain().block)
        splitBlock = buildingblocks.Block(transaction, H(str.encode(serial)).hexdigest(), isSplit=True)
        for node in self.nodes:
            node.chain.addBlock(splitBlock)

        # create a new blockchain for all nodes that are in the new community
        newBlock = buildingblocks.Block(newTransaction, None)
        for node in newCommunityNodes:
            newBlockChain = blockchain.BlockChain()
            newBlockChain.setGenesis(newBlock)
            node.setBlockChain(newBlockChain)

        community1 = Community(self.network, random.randint(0,10**10), pool=self.pool, 
                               keys=None, nodeList=self.nodes)
        community2 = Community(self.network, random.randint(0,10**10), pool=self.pool, 
                               keys=None, nodeList=newCommunityNodes)
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

    # helper function to write the genesis transaction
    # new_chain_balances: pubkey -> balance dict
    def writeGenesisSplitTransaction(self, new_chain_balances):
        inp = []
        out = []
        total = 0

        # create a new output genesis transaction with the balances owned by each pubkey as output
        for key in new_chain_balances.keys():
            coins = new_chain_balances[key]
            out.append({"value": coins, "pubkey": key})
            total += coins

        sig = H(str.encode(str(inp) + str(out))).hexdigest()
        number = H(str.encode(str(inp) + str(out) + sig)).hexdigest()
        transaction = buildingblocks.Transaction(number, inp, out, sig)

        return transaction, total

    # helper function to create the split transaction
    # old_chain_to_zero: list of (values, pubkey) tuples of outputs from chain that were spent
    # old_chain_retain:  list of (values, pubkey) tuples of outputs from chain that were not spent
    def writeSplitTransaction(self, old_chain_to_zero, old_chain_retain):
        inp = []
        out = []
        input_val = 0
        output_val = 0
        output_pairs = [item for item in old_chain_retain if item not in old_chain_to_zero]

        # set put all viable outputs to the input of this new transaction
        for (value, pubkey) in old_chain_retain:
            inp.append({"value": value, "pubkey": pubkey})
            input_val += value

        # set all inputs not remaining in the old chain to output to 0
        for (value, pubkey) in old_chain_to_zero:
            out.append({"value": 0, "pubkey": pubkey})

        # set all inputs remaining in the old chain to output to their original output value
        for (value, pubkey) in output_pairs:
            out.append({"value": value, "pubkey": pubkey})
            output_val += value

        sig = H(str.encode(str(inp) + str(out))).hexdigest()
        number = H(str.encode(str(inp) + str(out) + sig)).hexdigest()
        transaction = buildingblocks.Transaction(number, inp, out, sig)

        if input_val > output_val:
            return transaction, input_val - output_val
        else:
            print("ERROR TRANSACTION INPUT GREATER THAN OUTPUT")

    # generates a pair of transactions (genesis, split) where the genesis transaction is the initial transaction
    # for the new community and split is the next transaction for the original community
    # pubkeys = list of public keys in the new community (split community)
    def generateSplitTransactions(self, pubkeys):
        block = self.fetchUpToDateBlockchain().longestChain().block
        new_chain_balances = defaultdict(int)  # {pubkey: balance} dict for new genesis block
        old_chain_to_zero = []  # list of (pubkey, value) pairs that are added to new genesis block
        old_chain_spent = []  # helper list for transactions that are spent (inputs in a block on chain)
        old_chain_retain = []  # list of (pubkey, value) pairs that are still valid to be used as inputs

        while True:
            tx = utils.Utils.deserializeTransaction(block.tx)
            out = tx.out
            inp = tx.inp

            # iterate through all inputs and remove them as viable balances
            for item in inp:
                pubkey = item["pubkey"]
                value = item["value"]
                tx = (value, pubkey)

                # add transaction to spent transactions list of old chain
                old_chain_spent.append(tx)

                # remove already spent transaction from initial balance of new chain
                # should be no overflow error since using python
                if pubkey in pubkeys:
                    new_chain_balances[pubkey] -= value

            # iterate through all outputs and add them as viable balances
            for item in out:
                pubkey = item["pubkey"]
                value = item["value"]
                tx = (value, pubkey)

                # check if transaction has been spent, if not add to retained transactions
                if tx in old_chain_spent:
                    old_chain_spent.remove(tx)
                else:
                    old_chain_retain.append(tx)
                    # if transaction will be added to new community, add to list of transactions that will be zeroed
                    if pubkey in pubkeys:
                        old_chain_to_zero.append(tx)

                # add output transaction to initial balance of new chain
                if pubkey in pubkeys:
                    new_chain_balances[pubkey] += value

            # check if current block is a genesis block or split block, if so all transactions prior should be
            # accounted for so stop
            if not block.isGenesis and not block.isSplit:
                block = block.prev
                continue
            else:
                break

        # final check to see if any spent(input) transactions remain suggesting a double spend
        if len(old_chain_spent) == 0:
            split_tx, sent_to_gen = self.writeSplitTransaction(old_chain_to_zero, old_chain_retain)
            gen, total = self.writeGenesisSplitTransaction(new_chain_balances)
            if sent_to_gen == total:
                return split_tx, gen
            else:
                print("ERROR GENESIS TRANSACTION VALUE NOT EQUAL TO ORIGINAL BALANCES SUM")
        else:
            print("ERROR SPENT TRANSACTION ADDED TO NEW BALANCE")