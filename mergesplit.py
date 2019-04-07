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


class Transaction:
    def __init__(self, number, inp, out, sig):
        self.number = number
        self.inp = inp
        self.out = out
        self.sig = sig


class Block:
    def __init__(self, tx, prev, isGenesis=False, isFee=False):
        self.tx = tx;
        self.prev = prev;
        self.isGenesis = isGenesis
        self.isFee = isFee


class BlockNode:
    def __init__(self, block=None, prev=None):
        self.block = block
        self.prev = prev


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


class Utils:
    
    # utility method to validate legal transaction files
    def validateLegalTransaction(transactionHash):
        if not isinstance(transactionHash, dict):
            return False
        if ('number' not in transactionHash
            or 'input' not in transactionHash
            or 'output' not in transactionHash
            or 'sig' not in transactionHash
            or len(transactionHash) != 4):
            return False
        if (not isinstance(transactionHash['input'], list)
            or not isinstance(transactionHash['output'], list)
            or not isinstance(transactionHash['number'], str)
            or not isinstance(transactionHash['sig'], str)):
            return False
        for inp in transactionHash['input']:
            if (not isinstance(inp, dict)
                or 'number' not in inp
                or 'output' not in inp
                or len(inp) != 2):
                return False
            if (not isinstance(inp['output'], dict)
                or 'value' not in inp['output']
                or 'pubkey' not in inp['output']
                or len(inp['output']) != 2):
                return False
            if (not isinstance(inp['number'], str)
                or not isinstance(inp['output']['value'], numbers.Number)
                or not isinstance(inp['output']['pubkey'], str)):
                return False
        for out in transactionHash['output']:
            if (not isinstance(out, dict) 
                or not 'value' in out
                or not 'pubkey' in out
                or len(out) != 2):
                return False
            if (not isinstance(out['value'], numbers.Number)
                or not isinstance(out['pubkey'], str)):
                return False
        return True
    
    # utility method to read in transactions from input file
    def readTransactionFile(filename):
        transactions = []
        with open(filename) as f:
            data = json.load(f)
            for t in data:
                if Utils.validateLegalTransaction(t):
                    transaction = Transaction(t["number"], t["input"], t["output"], t["sig"])
                    transactions.append(transaction)
        return transactions
    
    # utility method to serialize a transaction
    def serializeTransaction(transaction):
        toSerialize = [transaction.number, transaction.inp, transaction.out, transaction.sig]
        wrapped = {'data': toSerialize}
        data = json.dumps(wrapped)
        return data
    
    # utility method to serialize a block
    def serializeBlock(block):
        toSerialize = [block.tx, block.prev]
        wrapped = {'data': toSerialize}
        data = json.dumps(wrapped)
        return data
     
    # utility method to deserialize a block
    def deserializeBlock(block):
        wrapped = json.loads(block)
        wrapped = wrapped['data']
        return Block(wrapped[0], wrapped[1])
        
    # utility method to deserialize a transaction
    def deserializeTransaction(tx):
        wrapped = json.loads(tx)
        wrapped = wrapped['data']
        return Transaction(wrapped[0], wrapped[1], wrapped[2], wrapped[3])
    
    # utility method to verify if public key can validate a message given its signature
    def verifyWithPublicKey(pubkey, message, signature):
        try:
            verifyKey = str.encode(pubkey)
            verifyKey = nacl.signing.VerifyKey(verifyKey,
                                               encoder=nacl.encoding.HexEncoder)
            sig = str.encode(signature)
            bytesMessage = str.encode(str.encode(message).hex())
            # verify the message and signature using the public key
            verifyKey.verify(bytesMessage, sig, encoder=nacl.encoding.HexEncoder)
        except:
            return False
        return True


# represents a forger who validates blocks and adds them to the blockchain
# accrues transaction fees for proposing merges/splits that get accepted
class Node:
    
    def __init__(self, publicKey, privateKey, community):
        # public key address to reference node
        self.publicKey = publicKey
        # private key address to reference node
        self.privateKey = privateKey
        # private reference to network this node is part of
        self.network = community.network
        # private reference to community node is part of
        self.community = community
        # node's stake in the system (for proof of stake)
        self.stake = 0
        # wait time before sending asynchronous merge/split proposals
        self.wait = random.randrange(self.network.requestTimeout)
        # reference node's blockchain
        self.chain = BlockChain()
        # restart for locking on merge/split proposals
        self.restart = False
        # scheduler to send asynchronous merge/split proposals
        self.sched = Scheduler()

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
                self.network.merge(self.community, neighbor)

    # node proposal to split a community into two new communites in the network
    def proposeSplit(self):
        if self.network.canSplit(self.community):
            self.network.split(self.community)
    
    # checks if the transaction does not already exist on this chain
    def checkNewTransaction(self, transaction, prev):
        current = prev
        while current:
            currentTransaction = Utils.deserializeTransaction(current.block.tx)
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
                currentTransaction = Utils.deserializeTransaction(current.block.tx)
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
                Utils.verifyWithPublicKey(publicKeySender, message, transaction.sig)
            except:
                return False
        return True
    
    # check whether each output actually exists in the named transaction
    def checkOutputExistsForInput(self, transaction, prev):
        for inp in transaction.inp:
            current = prev
            while current:
                currentTransaction = Utils.deserializeTransaction(current.block.tx)
                if currentTransaction.number == inp['number']:
                    break
                current = current.prev
            if current:
                currentTransaction = Utils.deserializeTransaction(current.block.tx)
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
                currentTransaction = Utils.deserializeTransaction(current.block.tx)
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
        for transaction in self.network.pool:
            tx = Utils.serializeTransaction(transaction)
            if self.validate(transaction, self.chain.longestChain()):
                return True
        return False
    
    # verifies whether a proposed block can be added to the blockchain
    def verifyProposal(self, proposedBlock):
        tx = Utils.deserializeTransaction(proposedBlock.tx)
        # next verify if this block can be added to a chain
        # and if the transaction contained in the block is valid
        if (self.chain.isValidPrev(proposedBlock.prev)
            and self.validate(tx, self.chain.blockToNode[proposedBlock.prev], proposedBlock.isFee)):
            return True
        return False

# represents an individual network/subgroup of nodes/transaction pools
class Community:
    
    def __init__(self, network, keys):
        # store parent network this community is a part of
        self.network = network
        # number of nodes/forgers in community
        self.nodeCount = len(keys)
        # stores the forgers
        self.nodes = []
        # quick lookup for nodes based on public key address
        self.nodeLookup = {}
        # community's unique transaction pool
        self.pool = []
        # create constituent nodes of community
        for i in range(self.nodeCount):
            node = Node(keys[i][0], keys[i][1], self)
            self.nodes.append(node)
            self.nodeLookup[keys[i][0]] = node

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
                    prev = H(str.encode(Utils.serializeBlock(self.chain.longestChain().block))).hexdigest()
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
        prev = H(str.encode(Utils.serializeBlock(self.chain.longestChain().block))).hexdigest()
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
        pass
    
    ### TODO: implement splitting functionality
    def split(self):
        pass


# parent network that holds constituent disjoint communities
class Network:

    # model file for mergesplit merge model
    mergeModelPath = "/models/mergesplit_merge.pkl"
    # model file for mergesplit split model
    splitModelPath = "/models/mergesplit_split.pkl"
    # prediction threshold for mergesplit models to recommend an action
    predictionThreshold = 0.6
    # nodes must wait for random timeout between 0 and requestTimeout seconds
    # before sending successive mergesplit proposals (combats DOS attacks)
    requestTimeout = 60
    # mergesplit fee to reward for proposing accepted merges/splits (inventive scheme)
    mergeSplitFee = 5
    
    def __init__(self, communities):
        # stores disjoint communties in the network
        self.communities = communities
        # stores running thread for each community
        self.threads = []
        # set executable thread for each community
        for community in communities:
            self.threads.append(Thread(target=community.run, name='Node {}'.format(i)))
        # load mergesplit merge model
        self.mergeModel = joblib.load(self.mergeModelPath)
        # load mergesplit split model
        self.splitModel = joblib.load(self.splitModelPath)
        # lock prevents multiple merges/splits from executing at the same time
        self.lock = Lock()

    # executes a merge proposed by proposer between community1 and community2 
    def merge(self, proposer, community1, community2):
        # acquire lock to ensure that more than 1 merge/split can be executed at once
        self.lock.acquire()
        try:
            # check if a merge/split was not just executed
            if not proposer.restart:
                # try to execute the merge
                # returns status of operation and the new merged community if successful
                approved, community = community1.merge(community2)
                if approved:
                    # if successful, proposer accrues a mergesplit transaction fee
                    community.accrueTransactionFee(proposer)
        finally:
            # if the merge/split was not just executed (by another node)
            if not proposer.restart:
                # reset the nodes
                for c in self.communities:
                    for node in c.nodes:
                        # indicate for other nodes about to acquire the lock
                        # to give up their claim to it
                        node.restart = True
                        # randomly assign a timeout period to every node in the community
                        # before sending another merge/split proposal
                        node.wait = random.randrange(self.requestTimeout)
                        node.setRequestTimeout()
            # release lock allowing merge/splits to be proposed again
            self.lock.release()
            proposer.restart = False

    # executes a split proposed by proposer for community
    def split(self, proposer, community):
        # acquire lock to ensure that more than 1 merge/split can be executed at once
        self.lock.acquire()
        try:
            # check if a merge/split was not just executed
            if not proposer.restart:
                # try to execute the split
                # returns status of operation and the two split communities if successful
                approved, community1, community2 = community.split()
                if approved:
                    # if successful and community1 contains the proposer
                    if community1.contains(proposer.publicKey):
                        # proposer in community1 accrues the transaction fee
                        community1.accrueTransactionFee(proposer)
                    else:
                        # proposer in communit2 accrues the transaction fee
                        community2.accrueTransactionFee(proposer)
        finally:
            # if the merge/split was not just executed (by another node)
            if not proposer.restart:
                for c in self.communities:
                    # indicate for other nodes about to acquire the lock
                    # to give up their claim to it
                    for node in c.nodes:
                        # indicate for other nodes about to acquire the lock
                        # to give up their claim to it
                        node.restart = True
                        # randomly assign a timeout period to every node in the community
                        # before sending another merge/split proposal
                        node.wait = random.randrange(self.requestTimeout)
                        node.setRequestTimeout()
            # release lock allowing merge/splits to be proposed again
            self.lock.release()
        proposer.restart = False

    # run ML classification of merge utility (novel incentive scheme)
    def scoreMerge(self, community1, community2):
        # store number of nodes, length of longest chain, number of forks,
        # and total stake in system for forgers in communities to be merged
        numberOfNodes1, longestChain1, numberOfForks1, totalStake1 = len(community1.nodes), 0, 0, 0
        numberOfNodes2, longestChain2, numberOfForks2, totalStake2 = len(community2.nodes), 0, 0, 0
        for node in community1.nodes:
            longestChain1 = max(longestChain1, node.chain.lengthOfLongestChain())
            numberOfForks1 = max(numberOfForks1, len(node.chain.chains))
            totalStake1 += node.stake
        for node in community2.nodes:
            longestChain2 = max(longestChain2, node.chain.lengthOfLongestChain())
            numberOfForks2 = max(numberOfForks2, len(node.chain.chains))
            totalStake2 += node.stake
        # construct the test example
        X = np.asarray([numberOfNodes1, numberOfNodes2,
                        longestChain1, longestChain2,
                        numberOfForks1, numberOfForks2,
                        totalStake1, totalStake2])
        # run model prediction to classify merge utility
        return self.mergeModel.predict(X)

    # run ML classification of split utility (novel incentive scheme)
    def scoreSplit(self, community):
        # store number of nodes, length of longest chain, number of forks,
        # and total stake in system for forgers in community to be split
        numberOfNodes, longestChain, numberOfForks, totalStake = len(community.nodes), 0, 0, 0
        for node in community.nodes:
            longestChain = max(longestChain, node.chain.lengthOfLongestChain())
            numberOfForks = max(numberOfForks, len(node.chain.chains))
            totalStake += node.stake
        # construct the test example
        X = np.asarray([numberOfNodes, longestChain, numberOfForks, totalStake])
        # run model prediction to classify split utility
        return self.splitModel.predict(X)

    # validate that two communities can be merged
    def canMerge(self, community1, community2):
        if community1 == community2:
            return False
        # check if merge op is legal
        # TODO: implement merge validation logic
        # ADD CODE HERE
        score = self.scoreMerge(community1, community2)
        # return whether model score > threshold to recommend the merge
        return score > self.predictionThreshold

    # validate that a community can be split
    def canSplit(self, community):
        # check if split op is legal
        # TODO: implement split validation logic
        # ADD CODE HERE
        score = self.scoreSplit(community)
        # return whether model score > threshold to recommend the split
        return score > self.predictionThreshold