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
import mergesplit_node
import mergesplit_network
import mergesplit_community
import buildingblocks


# utility class that permits SerDes operations, signing verification, IO parsing
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

    def parseTransactions(pool):
        transactions = []
        for t in pool:
            if Utils.validateLegalTransaction(t):
                transaction = buildingblocks.Transaction(t["number"], t["input"], t["output"], t["sig"])
                transactions.append(transaction)
        return transactions
    
    # utility method to read in transactions from input file
    def readTransactionFile(filename):
        communities = []
        with open(filename) as f:
            data = json.load(f)
            for community in data:
                pool, keys = community["pool"], community["signingKeys"]
                transactions = Utils.parseTransactions(pool)
                communities.append(mergesplit_community.Community(network=None, id=-1, pool=transactions,
                                                                  keys=keys, nodeList=None))
        return communities
    
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
        return buildingblocks.Block(wrapped[0], wrapped[1])
        
    # utility method to deserialize a transaction
    def deserializeTransaction(tx):
        wrapped = json.loads(tx)
        wrapped = wrapped['data']
        return buildingblocks.Transaction(wrapped[0], wrapped[1], wrapped[2], wrapped[3])
    
    # utility method to generate random 256 bit nonces
    def generateNonce(length=256):
        return ''.join([str(random.randint(0,9)) for i in range(length)])

    # utility method to verify if public key can validate a message given its signature
    def verifyWithPublicKey(pubkey, message, signature):
        try:
            verifyKey = str.encode(pubkey)
            verifyKey = nacl.signing.VerifyKey(verifyKey, encoder=nacl.encoding.HexEncoder)
            sig = str.encode(signature)
            bytesMessage = str.encode(str.encode(message).hex())
            # verify the message and signature using the public key
            verifyKey.verify(bytesMessage, sig, encoder=nacl.encoding.HexEncoder)
        except:
            return False
        return True