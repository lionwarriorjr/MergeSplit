# MergeSplit
#### Authors: Srihari Mohan, Steven Zhang, Ben Pikus, Kevin Peng
An implementation of the custom MergeSplit Blockchain Protocol for JHU 601.641/441 Blockchains and Cryptocurrencies. Accommodates arbitrary merging and splitting of disjoint blockchains in a network to allow an arbitrary favoring of security over scalability or vice versa during processing of the network. A novel incentive scheme encourages miners to merge/split the blockchain at different points in time to encourage the optimal balance between high security and high throughput.

network.py:
<br/>Implements overarching MergeSplit network that contains disjoint communities. The Network class is the driver from which merges and splits get proposed to, and the triggers merges and splits to be validated (and if approved) get executed. Trained models for the MergeSplit incentive scheme are deserialized in Network and used in the execution of the merges/splits in this file.

community.py:
<br/>The Community class represents an individual network/subgroup of nodes and transactions. Each community is a disjoint component of the network with an isolated set of forgers and its own transaction pool. The Community class holds the driver run() function that gets loaded into each thread context to be executed asynchronously. It also implements the logic behind accrual of transaction fees for nodes that propose accepted merges/splits to help the MergeSplit network maintain constituent blockchains with an optimal balance between high throughput and high security in a decentralized fashion. The core merging and splitting functionality is implemented here.

node.py:
<br/>The Node class implements the functionality of a node/forger/miner. Each node validates transactions in its communities and can accrue transaction fees when proposing merges/splits that get accepted by the network. Each node contains its own internal representation of a blockchain, and asynchronously proposes merges/splits according to randomly set timeout periods.

blockchain.py:
<br/>The Blockchain class implements the blockchain (included as a field of every node).

buildingblocks.py:
<br/>This file holds building blocks referenced in every other file, including MergeSplit's representation of a transaction, block, and block node.

utils.py:
<br/>The Utils class holds static methods that implement utility functions like parsing input/output, serializing/deserializing blocks and transactions, and verifying message signatures.
