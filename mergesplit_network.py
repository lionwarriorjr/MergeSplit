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
import blockchain
import utils
import mergesplit_node
import mergesplit_community
import buildingblocks


# implements a parent network that holds constituent disjoint communities
class Network:

    # model file for mergesplit merge model
    mergeModelPath = "/models/mergesplit_merge.pkl"
    # model file for mergesplit split model
    splitModelPath = "/models/mergesplit_split.pkl"
    # prediction threshold for mergesplit models to recommend an action
    predictionThreshold = 0.6
    # mergesplit fee to reward for proposing accepted merges/splits (inventive scheme)
    mergesplitFee = 5
    
    def __init__(self, communities):
        # stores disjoint communties in the network
        self.communities = communities
        # stores running thread for each community
        self.threads = []
        # set executable thread for each community
        for i in range(len(communities)):
            community = communities[i]
            self.threads.append(Thread(target=community.run, name='Node {}'.format(i)))
        # load mergesplit merge model
        #self.mergeModel = joblib.load(self.mergeModelPath)
        # load mergesplit split model
        #self.splitModel = joblib.load(self.splitModelPath)
        self.mergeModel = None
        self.splitModel = None
        self.numMerges = 0 # number of executed merges
        self.numSplits = 0 # number of executed splits
    
    def summarize(self):
        print('MergeSplit Network Summary:')
        print(str(len(self.communities)) + ' communities loaded into network')
        for community in self.communities:
            keys = [node.publicKey for node in community.nodes]
            print('community ' + str(community.id) + ': ' + str(keys))
            print(str(len(community.pool)) + ' transactions loaded into pool')
            active = sum([thread.isAlive() for thread in self.threads])
            print(str(active) + ' threads currently active')
            
    def _removeCommunity(self, id):
        index = -1
        for i, community in enumerate(self.communities):
            if community.getCommunityId() == id:
                index = i
        if index != -1:
            self.communities.pop(index)
        
    # executes a merge proposed by proposer between community1 and community2 
    def merge(self, proposer, community1, community2):
        # try to execute the merge
        # returns status of operation and the new merged community if successful
        (approved, community) = community1.merge(community2)
        if approved:
            # if successful, proposer accrues a mergesplit transaction fee
            community.accrueTransactionFee(proposer)
            self._removeCommunity(community2.getCommunityId())
            self.numMerges += 1
            
    # executes a split proposed by proposer for community
    def split(self, proposer, community):
        # try to execute the split
        # returns status of operation and the two split communities if successful
        (approved, community1, community2) = community.split()
        if approved:
            # if successful and community1 contains the proposer
            if community1.contains(proposer.publicKey):
                # proposer in community1 accrues the transaction fee
                community1.accrueTransactionFee(proposer)
            else:
                # proposer in community2 accrues the transaction fee
                community2.accrueTransactionFee(proposer)
            # remove old community from the network and add in the two new ones
            self._removeCommunity(community.getCommunityId())
            self.communities.append(community1)
            self.communities.append(community2)
            self.numSplits+= 1

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
        #score = self.scoreMerge(community1, community2)
        # return whether model score > threshold to recommend the merge
        #return score > self.predictionThreshold

        return True

    # validate that a community can be split
    def canSplit(self, community):
        # check if split op is legal
        # TODO: implement split validation logic
        # ADD CODE HERE
        #score = self.scoreSplit(community)
        # return whether model score > threshold to recommend the split
        #return score > self.predictionThreshold

        return True