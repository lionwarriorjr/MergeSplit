import sys
import os
import time
import json
import numbers
from hashlib import sha256 as H
import random
from random import choice
import nacl.signing
import nacl.encoding
from nacl.public import PrivateKey
from utils import Utils
from mergesplit_node import Node
from mergesplit_community import Community
from buildingblocks import Transaction, Block


MAX_TRANSACTION_THRESHOLD = 100
MAX_INPUT_LIMIT = 1e6

# utility class to generate input data conformant to MergeSplit analysis
def split_money(target, nodeLimit):
    numberNodes = random.randint(1, nodeLimit)
    remaining = target
    result = []
    while remaining > 0 and len(result) < nodeLimit-1:
        remove = random.randint(1, remaining)
        result.append(remove)
        remaining -= remove
    if remaining > 0:
        result.append(remaining)
    return result

def generateKeys(totalNodes):
    pubkeys, prikeys = [], []
    for i in range(totalNodes):
        prikey = nacl.signing.SigningKey.generate()
        # Obtain the verify key for a given signing key
        pubkey = prikey.verify_key
        # Serialize the verify key to send it to a third party
        pubkey = pubkey.encode(encoder=nacl.encoding.HexEncoder)
        pubkeys.append(str(pubkey, 'utf-8'))
        prikeys.append(prikey)
    pubkeyMap = {}
    for i in range(totalNodes):
        pubkeyMap[pubkeys[i]] = i
    return pubkeys, prikeys, pubkeyMap

def createGenesisTransaction(transactionList, result, pubkeys):
    inp, out = [], []
    for pubkey in pubkeys:
        coins = random.randint(1,100)
        out.append({"value": coins, "pubkey": pubkey})
    sig = H(str.encode(str(inp) + str(out))).hexdigest()
    number = H(str.encode(str(inp) + str(out) + sig)).hexdigest()
    transaction = Transaction(number, inp, out, sig)
    transactionList.append(transaction)
    transactionAsJSON = {'number': number, 'input': inp, 'output': out, 'sig': sig}
    result.append(transactionAsJSON)

def generateTransactions(transactionList, result, 
                         totalNodes, totalTransactions,
                         pubkeys, prikeys, pubkeyMap):
    for i in range(1, totalTransactions):
        inputSum = 0
        transaction = transactionList[len(transactionList)-1]
        receiver = random.randint(0, len(transaction.out)-1)
        pubkeyReceiver = transaction.out[receiver]['pubkey']
        receiverInput, receiverOutput = [], []
        for receiverTransaction in transactionList:
            if (len(receiverInput) == MAX_TRANSACTION_THRESHOLD
                or inputSum >= MAX_INPUT_LIMIT):
                break
            elif receiverTransaction == transaction:
                continue
            for out in receiverTransaction.out:
                if (len(receiverInput) == MAX_TRANSACTION_THRESHOLD
                    or inputSum >= MAX_INPUT_LIMIT):
                    break
                if out['pubkey'] == pubkeyReceiver:
                    choose = choice([True, False])
                    if choose:
                        receiverInput.append({"number": receiverTransaction.number, 
                                              "output": {"value": out['value'], "pubkey": pubkeyReceiver}})
                        inputSum += out['value']
        if not receiverInput:
            receiverInput.append({"number": transaction.number, 
                                  "output": {"value": transaction.out[receiver]['value'], "pubkey": pubkeyReceiver}})
            inputSum += transaction.out[receiver]['value']
        x = split_money(inputSum, totalNodes)
        ids = random.sample(range(totalNodes), len(x))
        for j in range(len(x)):
            receiverOutput.append({"value": x[j], "pubkey": pubkeys[ids[j]]})
        serializedInput = "".join([str(inp['number']) + str(inp['output']['value']) + str(inp['output']['pubkey'])
                                  for inp in receiverInput])
        serializedOutput = "".join([str(out['value']) + str(out['pubkey']) for out in receiverOutput])
        message = str.encode(serializedInput + serializedOutput)
        prikey = prikeys[pubkeyMap[pubkeyReceiver]]
        signed = prikey.sign(message, encoder=nacl.encoding.HexEncoder)
        sig = str(signed.signature, 'utf-8')
        number = H(str.encode(serializedInput + serializedOutput + sig)).hexdigest()
        nextTransaction = Transaction(number, receiverInput, receiverOutput, sig)
        transactionList.append(nextTransaction)
        transactionAsJSON = {'number': number, 'input': receiverInput, 'output': receiverOutput, 'sig': sig}
        result.append(transactionAsJSON)

def run(totalCommunities, nodesPerCommunity, transactionLimitPerCommunity):
    result = []
    for i in range(totalCommunities):
        pubkeys, prikeys, pubkeyMap = generateKeys(nodesPerCommunity)
        transactionList, current = [], []
        createGenesisTransaction(transactionList, current, pubkeys)
        generateTransactions(transactionList, current, 
                             nodesPerCommunity, transactionLimitPerCommunity,
                             pubkeys, prikeys, pubkeyMap)
        keys = []
        for i in range(len(pubkeys)):
            prikey = prikeys[i].encode(encoder=nacl.encoding.HexEncoder).decode()
            keys.append([pubkeys[i], prikey])
        community = {'pool': current, 'signingKeys': keys}
        result.append(community)
    return result

def main():
    totalCommunities = int(sys.argv[1])
    nodesPerCommunity = int(sys.argv[2])
    transactionLimitPerCommunity = int(sys.argv[3])
    start = time.time()
    result = run(totalCommunities, nodesPerCommunity, transactionLimitPerCommunity)
    end = time.time()
    filename = ("input/communities_" + str(totalCommunities) + "_nodes_" + 
                str(nodesPerCommunity) + "_transactions_" + str(transactionLimitPerCommunity) + ".txt")
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    with open(filename, 'w') as outfile:
        json.dump(result, outfile, sort_keys=False, indent=4, ensure_ascii=False)
        outfile.close()
    print("Transaction file generated (contains double spends): " + filename)
    print("time to generate inputs (sec): " + str(end-start))
    
if __name__== "__main__":
    main()
