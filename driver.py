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


class Driver:
    
    def __init__(self, filename):
        self.filename = filename
        self.parseCommunities()

    def parseCommunities(self):
        communities = Utils.parseCommunities(self.filename)
        self.network = Network(communities)
        for i in range(len(communities)):
            self.network.communities[i].id = i
            self.network.communities[i].network = self.network
    
    def createGenesisBlock(self, transaction):
        tx = Utils.serializeTransaction(transaction)
        # generate arbitrary prev
        prev = Utils.generateNonce()
        return Block(tx, prev, isGenesis=True)

    # reads transactions from input file, creates genesis blow in each node's blockchain,
    # and adds remaining transactions to global, unverified transaction pool
    def initializeSimulation(self):
        for community in self.network.communities:
            pool = community.pool
            if (len(pool) == 0):
                raise NameError('Transaction list for community ' + str(community.id) + ' is empty!')
            # create genesis block
            genesis = self.createGenesisBlock(pool.pop(0))
            # adds genesis to each node's blockchain
            for node in community.nodes:
                node.chain.setGenesis(genesis)
        self.network.summarize()
        return True
    
    # starts up all threads and runs them
    # simulates network activity
    def simulate(self):
        self.initializeSimulation()
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
    driver = Driver(sys.argv[1]))
    # run the driver (simulate network activity with threads)
    driver.simulate()
    
    # log stats after completion
    print(str(len(driver.network.threads)) + " threads spun up")
    # logs the length of the longest chain (valid blockchain)
    
    for community in driver.network.communities:
        print("Length of Verified Ledger for community " + str(community.id) + ": " + 
              str(community.checkForMatchedSequences()))
    
    # log each node's blockchain to a file (in output/{nodeCount} directory)
    root = sys.argv[2]
    for community in driver.network.communities):
        filePrefix = root + "/community" + str(community.id)
        for i in range(len(community.nodes)):
            filename = filePrefix + "/blockchains_node" + str(i+1) + ".json"
            os.makedirs(os.path.dirname(filename), exist_ok=True)
            node.chain.log(filename)

if __name__== "__main__":
    main()