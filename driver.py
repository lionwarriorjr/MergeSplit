import sys
import os
import time
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
import blockchain
import utils
import mergesplit_node
import mergesplit_community
import mergesplit_network
import buildingblocks


# implements main driver function to simulate MergeSplit activity in a network
class Driver:
    
    def __init__(self, filename):
        self.filename = filename
        self.parseCommunities()

    def parseCommunities(self):
        communities = utils.Utils.readTransactionFile(self.filename)
        self.network = mergesplit_network.Network(communities)
        for i in range(len(communities)):
            self.network.communities[i].id = i
            self.network.communities[i].network = self.network
            for node in self.network.communities[i].nodes:
                node.network = self.network
    
    def createGenesisBlock(self, transaction):
        tx = utils.Utils.serializeTransaction(transaction)
        # generate arbitrary prev
        prev = utils.Utils.generateNonce()
        return buildingblocks.Block(tx, prev, isGenesis=True)

    # reads transactions from input file, creates genesis blow in each node's blockchain,
    # and adds remaining transactions to global, unverified transaction pool
    def initializeSimulation(self):
        for community in self.network.communities:
            pool = community.pool
            print(len(pool))
            if (len(pool) == 0):
                raise NameError('Transaction list for community ' + str(community.id) + ' is empty!')
            # create genesis block
            genesisTransaction = pool.pop(0)
            genesisBlock = self.createGenesisBlock(genesisTransaction)
            # adds genesis to each node's blockchain
            for node in community.nodes:
                node.chain.setGenesis(genesisBlock)
            community.updateStake(genesisTransaction)
        self.network.summarize()
        return True
    
    # starts up all threads and runs them
    # simulates network activity
    def simulate(self):
        self.initializeSimulation()
        print('\ninitialized simulation')
        # start up threads
        for i in range(len(self.network.threads)):
            self.network.threads[i].start()
        # wait for all threads to finish before exiting
        for i in range(len(self.network.threads)):
            self.network.threads[i].join()


# main driver to instantiate MergeSplit driver class and simulate network activity with threads
# receives as command-line arguments the input file and output directory to store logged blockchains
def main():
    # instantiate blockchains main driver
    driver = Driver(sys.argv[1])
    # run the driver (simulate network activity with threads)
    start = time.time()
    driver.simulate()
    end = time.time()
    
    # log stats after completion
    print(str(len(driver.network.threads)) + " threads spun up")
    # logs the length of the longest chain (valid blockchain)
    
    print(str(len(driver.network.communities)) + ' communities exist after processing')
    for community in driver.network.communities:
        print("Length of Verified Ledger for community " + str(community.id) + ": " + str(community.checkForMatchedSequences()) )

    print('\nElapsed time (sec): ' + str(end-start))
    
    print("Executed: " + str(driver.network.numMerges) + " merges, " + str(driver.network.numSplits) + " splits")
    # log each node's blockchain to a file
    root = sys.argv[2]
    for community in driver.network.communities:
        filePrefix = root + "/community" + str(community.id)
        for i in range(len(community.nodes)):
            filename = filePrefix + "/blockchains_node" + str(i+1) + ".json"
            os.makedirs(os.path.dirname(filename), exist_ok=True)
            community.nodes[i].chain.log(filename)


if __name__== "__main__":
    main()
