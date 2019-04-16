import sys
import os
import json
import numbers
from hashlib import sha256 as H
import random
from random import choice
import nacl.signing
import nacl.encoding
from nacl.public import PrivateKey
from utils import Utils
from node import Node
from community import Community
from buildingblocks import Transaction, Block


def random_sum_to(n):
    a = random.sample(range(1, n), random.randint(1, n-1)) + [0, n]
    list.sort(a)
    return [a[i+1] - a[i] for i in range(len(a) - 1)]

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
        while inputSum <= 1:
            inputSum = 0
            transaction = transactionList[len(transactionList)-1]
            receiver = random.randint(0, len(transaction.out)-1)
            pubkeyReceiver = transaction.out[receiver]['pubkey']
            receiverInput, receiverOutput = [], []
            for receiverTransaction in transactionList:
                if receiverTransaction == transaction:
                    continue
                for out in receiverTransaction.out:
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
        x = random_sum_to(inputSum)
        while len(x) == 0 or len(x) > totalNodes:
            x = random_sum_to(inputSum)
        ids = random.sample(range(totalNodes), len(x))
        for i in range(len(x)):
            receiverOutput.append({"value": x[i], "pubkey": pubkeys[ids[i]]})
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
        ntrans = random.randint(1, transactionLimitPerCommunity)
        generateTransactions(transactionList, current, 
                             nodesPerCommunity, ntrans,
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
    result = run(totalCommunities, nodesPerCommunity, transactionLimitPerCommunity)
    filename = ("input/communities_" + str(totalCommunities) + "_nodes_" + 
                str(nodesPerCommunity) + "_transactions_" + str(transactionLimitPerCommunity) + ".txt")
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    with open(filename, 'w') as outfile:
        json.dump(result, outfile, sort_keys=False, indent=4, ensure_ascii=False)
        outfile.close()
    print("Transaction file generated (contains double spends): " + filename)
    
if __name__== "__main__":
    main()