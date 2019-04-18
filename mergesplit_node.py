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
import mergesplit_community
import mergesplit_network 
import buildingblocks


# implements a forger who validates blocks and adds them to the blockchain
# accrues transaction fees for proposing merges/splits that get accepted
class Node:
    
    def __init__(self, publicKey, privateKey, community):
        # public key address to reference node
        self.publicKey = publicKey
        # private key address to reference node
        signingKey = str.encode(privateKey)
        signingKey = nacl.signing.SigningKey(signingKey, encoder=nacl.encoding.HexEncoder)
        self.privateKey = signingKey
        # private reference to network this node is part of
        self.network = community.network
        # private reference to community node is part of
        self.community = community
        # node's stake in the system (for proof of stake)
        self.stake = 0
        # wait time before sending asynchronous merge/split proposals
        self.wait = random.randrange(mergesplit_network.Network.requestTimeout)
        # reference node's blockchain
        self.chain = blockchain.BlockChain()
        # restart for locking on merge/split proposals
        self.restart = False
        # scheduler to send asynchronous merge/split proposals
        self.sched = Scheduler()

    def setBlockChain(self, newBlockChain):
        self.chain = newBlockChain

    def getPublicKey(self):
        return self.publicKey

    def getStake(self):
        return self.stake

    # starts sending asynchronous merge/split proposals
    def setRequestTimeout(self):
        if self.scheduler.running:
            self.sched.shutdown(wait=False)
        self.sched.start()
        self.sched.add_interval_job(proposeMerge, seconds=self.wait)
        self.sched.add_interval_job(proposeSplit, seconds=self.wait)

    # node proposal to merge a community with another in the network
    def proposeMerge(self):
        if self.network.communities:
            neighbor = random.choice(self.network.communities)
            if self.network.canMerge(self.community, neighbor):
                #self.network.merge(self.community, neighbor)
                pass

    # node proposal to split a community into two new communites in the network
    def proposeSplit(self):
        if self.network.canSplit(self.community):
            #self.network.split(self.community)
            pass
    
    # checks if the transaction does not already exist on this chain
    def checkNewTransaction(self, transaction, prev):
        current = prev
        while current:
            currentTransaction = utils.Utils.deserializeTransaction(current.block.tx)
            if currentTransaction.number == transaction.number:
                return False
            current = current.prev
        return True
    
    # checks if number is a valid hash
    def checkForValidNumber(self, transaction):
        serializedInput = "".join([str(inp['number']) + str(inp['output']['value']) + str(inp['output']['pubkey'])
                                   for inp in transaction.inp])
        serializedOutput = "".join([str(out['value']) + str(out['pubkey']) for out in transaction.out])
        h = H(str.encode(serializedInput + serializedOutput + transaction.sig)).hexdigest()
        return h == transaction.number
    
    # checks to see if each input exists on the chain for this transaction
    def checkInputsForTransaction(self, transaction, prev):
        for inp in transaction.inp:
            current = prev
            while current:
                currentTransaction = utils.Utils.deserializeTransaction(current.block.tx)
                if currentTransaction.number == inp['number']:
                    break
                current = current.prev
            if not current:
                return False
        return True
    
    # checks signatures for each input of transaction and sees if can be signed off by the sender
    def checkSignatures(self, transaction, isFee=False):
        if isFee:
            return True
        elif not transaction.inp:
            return False
        inp = transaction.inp[0]
        publicKeySender = inp['output']['pubkey']
        for i in range(len(transaction.inp)):
            inp = transaction.inp[i]
            if inp['output']['pubkey'] != publicKeySender:
                return False
            try:
                # checks to see if public key sender can sign off on the signature of the transaction
                serializedInput = "".join([str(inp['number']) + str(inp['output']['value']) + str(inp['output']['pubkey'])
                                          for inp in transaction.inp])
                serializedOutput = "".join([str(out['value']) + str(out['pubkey']) for out in transaction.out])
                message = serializedInput + serializedOutput
                utils.Utils.verifyWithPublicKey(publicKeySender, message, transaction.sig)
            except:
                return False
        return True
    
    # check whether each output actually exists in the named transaction
    def checkOutputExistsForInput(self, transaction, prev):
        for inp in transaction.inp:
            current = prev
            while current:
                currentTransaction = utils.Utils.deserializeTransaction(current.block.tx)
                if currentTransaction.number == inp['number']:
                    break
                current = current.prev
            if current:
                currentTransaction = utils.Utils.deserializeTransaction(current.block.tx)
                found = False
                for out in currentTransaction.out:
                    if (out['value'] == inp['output']['value']
                        and out['pubkey'] == inp['output']['pubkey']):
                        found = True
                        break
                if not found:
                    return False
            else:
                return False
        return True
    
    # check for existence of double spend using this transaction along a chain
    def checkNoDoubleSpend(self, transaction, prev):
        for inp in transaction.inp:
            current = prev
            # iterate back along the chain for each input in the transaction
            while current:
                currentTransaction = utils.Utils.deserializeTransaction(current.block.tx)
                if currentTransaction.number == inp['number']:
                    break
                # check if an input along the chain matches the transaction input
                for currentInp in currentTransaction.inp:
                    if (currentInp['number'] == inp['number']
                        and currentInp['output']['pubkey'] == inp['output']['pubkey']
                        and currentInp['output']['value'] == inp['output']['value']):
                        # we are trying to spend coins that were already sent off
                        # this is a double spend
                        return False
                current = current.prev
        return True
    
    # checks for sum of inputs into a transaction matching sum of outputs leaving it
    def checkInputEqualsOutput(self, transaction, isFee=False):
        if isFee:
            return True
        inputSum, outputSum = 0, 0
        for inp in transaction.inp:
            inputSum += inp['output']['value']
        for out in transaction.out:
            outputSum += out['value']
        return inputSum == outputSum
    
    # checks if a transaction is valid when being added to a chain
    def validate(self, transaction, prev, isFee=False):
        return (
                self.checkNewTransaction(transaction, prev)
                and self.checkForValidNumber(transaction)
                and self.checkInputsForTransaction(transaction, prev) 
                and self.checkOutputExistsForInput(transaction, prev)
                and self.checkSignatures(transaction, isFee)
                and self.checkNoDoubleSpend(transaction, prev)
                and self.checkInputEqualsOutput(transaction, isFee)
        )
    
    # check if a transaction exists in pool that could be added to longest chain
    def validTransactionExists(self):
        for transaction in self.community.pool:
            tx = utils.Utils.serializeTransaction(transaction)
            if self.validate(transaction, self.chain.longestChain()):
                return True
        return False
    
    # verifies whether a proposed block can be added to the blockchain
    def verifyProposal(self, proposedBlock):
        tx = utils.Utils.deserializeTransaction(proposedBlock.tx)
        # next verify if this block can be added to a chain
        # and if the transaction contained in the block is valid
        if (self.chain.isValidPrev(proposedBlock.prev)
            and self.validate(tx, self.chain.blockToNode[proposedBlock.prev], proposedBlock.isFee)):
            return True
        return False

    # node gives approval for a split request
    def approveSplit(self, proposal):
        if random.randint(0, 4) == 0:
            return False
        return True

    # node gives approval for a merge request
    def approveMerge(self, proposal):
        if random.randint(0, 4) == 0:
            return False
        return True