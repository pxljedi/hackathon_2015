#debug flag. In production set debug="False"
debug = False
if debug == False:
    from django.shortcuts import render
    from django.utils import timezone
    from django.template import RequestContext

# imports
import httplib
import json
from os import path
from glob import glob
from pydvid import keyvalue as kv
from pydvid import general
import numpy

def callDVID(keyname, dataname='codingcircle'):
    server = "emrecon100.janelia.priv"
    uuid = '2a3'
    connection = httplib.HTTPConnection(server, timeout=30.0)
    keys = kv.get_keys(connection, uuid, dataname)
    if keyname not in keys:
        print "Invalid key", keyname
        return None
    return kv.get_value(connection, uuid, dataname, keyname)

def simple_view(request):
    today = "test"
    data_dictionary = {'today': today}
    my_template = 'hackathon_app/user_interface.html'
    my_data = getNeuronNames()
    return render(request,my_template,{'today':today,'data':my_data,},context_instance=RequestContext(request))

def charlottes_view(request):
    my_template = 'hackathon_app/user_interface.html'
    my_data = getNeuronNames()
    return render(request, my_template, {'data':my_data}, context_instance=RequestContext(request))

def clothoView(request):
    my_template = 'hackathon_app/user_interface.html'
    neuronList = getNeuronNames()
    combined = None
    types = None
    renderSvg = False
    if request.POST:
        reqVars = dict(request.POST.iterlists())
        neuronSearch = ["Tm9", "L3", "L2", "L4"]
        comboType = reqVars['combotype']
        neuronSearch = reqVars['neurons[]']
        #TODO replace values with values from request
        (combined, types) = processNeuronsRequest(neuronSearch, comboType[0])
        renderSvg = True
    data = {
        'neurons' : neuronList,
        'renderSvg' : renderSvg,
        'edges': combined,
        'nodes': types
    }
    print data['edges']
    return render(request, my_template, data, context_instance=RequestContext(request))


def getNeuronNames():
    data_file = callDVID('names.json')
    NeuronNames = json.loads(data_file)
    NeuronNames.sort()
    return NeuronNames

def processNeuronsRequest(neuronList, comboType):
    #test function
    #test=getInputsOutputs("16699")
    #return test
    #neuronList = ["Tm9", "L3", "L2", "L4"]
    #request contains neuron names and ids
    neuronNames = getNeuronNames() 
    #generate list of body ids user is interested in (use getBodyIds)
    #TODO replace with request.neuronList
    list_BodyId = getBodyId(neuronList)
    if debug:
        print "Neuron IDs:", list_BodyId 
    #for each body id, call getInputsOutputs
    #then call filterInputsOutputs to filter based on neuron list
    allIOs = getInputsOutputs(list_BodyId)
    filteredIOs = filterInputsOutputs(list_BodyId, allIOs)
    uncombinedOutputs = generateEdgeList(filteredIOs)
    #TODO replace sum with user selection from form
    (combined, types) = combineOutputs(uncombinedOutputs, comboType)
    return combined, types

#sample node list
if debug == True:
    neuronIDList = ["16699", "18631", "22077", "31699", "50809"]

def getInputsOutputs(neuronIDList):
    inputs_outputs = callDVID('inputs_output.json')
    in_out_dict = json.loads(inputs_outputs)
    #select neurons neuronIDList, puts them in a new dictionary, and return the dictionary to caller
    selected_nodes = {}
    for key in neuronIDList:
        thisNode = in_out_dict.get(key)
        selected_nodes[key] = thisNode
    return selected_nodes

def filterInputsOutputs(neuronIDs, inputsOutputs):
    #remove name
    #remove inputs come from neurons not neuronIDs list
    #remove outputs to neurons not in neuronIDs list
    #returns inputs and outputs that connect to neurons in listOfNeurons

    nodeIDs = inputsOutputs.keys();
    for item in nodeIDs:
        thisNode = inputsOutputs.get(item)

        #filter input nodes
        thisInputs = thisNode.get("inputs")
        thisInputskey = thisInputs.keys()

        for inputNode in thisInputskey:
            if (inputNode in neuronIDs):
                continue
            else:
                del thisInputs[inputNode]
        if debug == True:
            print  item + ": Inputs after filter " + str(len(thisInputs.keys()))
        #filter input nodes
        thisOutputs = thisNode.get("outputs")
        thisOutputskey = thisOutputs.keys()
        if debug == True:
            print  item + ": Outputs all " + str(len(thisOutputskey))
        for outputNode in thisOutputskey:
            if (outputNode in neuronIDs):
                continue
            else:
                del thisOutputs[outputNode]
        if debug == True:
            print  item + ": Outputs after filter " + str(len(thisOutputs.keys()))
        #delete name
        del thisNode["name"]
    return inputsOutputs
	
	
def getBodyId(neuronNames):
    data = callDVID('names_to_body_id.json')
    dic = json.loads(data)
    if neuronNames :
        ## Look up Body Id and add to the list
        lst = []
        for name in neuronNames:
            lst = lst + list(dic.get(name))
            #print lst
        if lst == []:
            return None
        nameSet = set(lst) # Remove duplicated id
        Newlst = list(nameSet)
        #print Newlst
        return Newlst
    else:
        return None
        #print 'None'


def generateEdgeList(listOfNeurons):
    #lei-ann
    #uses filterInputsOutputs to generate a list of connections for svg
    #per Charlott:  only use inputs edges in each node to avoid double counting
    #returns list of connections for svg

    #return a dict object consists of data structure
    #key = (thisNodeID-on-input-List, anotherNodeID-has-input-to-thisNode)#valuse{"destination": thisNodeID-on-input-List, "source": anotherNodeID-has-input-to-thisNode, "strength": inputStrength}
    inconnections = {}
    nodeIDs = listOfNeurons.keys()
    for nodeId in nodeIDs:
        node = listOfNeurons.get(nodeId)
        inputs = node.get("inputs")
        inputKeys = inputs.keys()
        for inputKey in inputKeys:
            strength = inputs.get(inputKey)
            if (strength > 0):
                idTuple = (nodeId, inputKey)
                edgeData = {"destination": nodeId, "source": inputKey, "strength": strength}
                inconnections[idTuple] = edgeData
    return inconnections

def combineOutputs(edgeList, combinationType):
	#combines nodes by cell type and calculates inputs and outputs base on combo type (mean, sum, etc.)
	#returns nodes, edges 
    #Ying Wu
    #new combinedOutputs for returning to caller (UI)
    combinedOutputs = {}
    #keys of input edgeList, in this list every element is unique, eg [("50809", "22077"), ("50809", "16699")]
    idTupleList = edgeList.keys()
    #paraell array for Neuron Type Tuples, in this list elements are not unique eg [('TM3', 'LD5'), ('TM3', 'LD5')]
    typeTupleList = []
    neuronsinfoJson = json.loads(callDVID('neuronsinfo.json', 'graphdata'))
    #print neuronsinfoJson
    for idTuple in idTupleList:
        #convert ID tuple to Type tuple
        typeTuple = neuronID2NeuronType(idTuple, neuronsinfoJson)
        #add typeTuple to typeTupleList
        typeTupleList.append(typeTuple)
    #combine output by cell type
    #build dictionary key=typeTuple, value = [strengths]
    for index, item in enumerate(typeTupleList):
        strength = edgeList.get(idTupleList[index]).get("strength")
        if item in combinedOutputs.keys():
            strength = edgeList.get(idTupleList[index]).get("strength")
            combinedOutputs.get(item).append(strength)
        else:
            #add an entry to combinedOutputs:  key=typeTuple, object = list of one strength
            combinedOutputs[item] = [strength]
    #now we have a new dictionary
    # key: cell type tuple,  value: strengths for this cell tuple in a list
    if(debug):
        print "before combine strength"
        print combinedOutputs
    # do math to combine strengths
    types = set()
    for item in combinedOutputs.keys():
        types.add(item[0])
        types.add(item[1])
        stregthList = combinedOutputs.get(item)
        strengthCombined = doMath(stregthList, combinationType)
        if strengthCombined:
            combinedDict = {"destination":item[0], "source":item[1], "strength":strengthCombined}
            combinedOutputs[item] = combinedDict
        else:
            del combinedOutputs[item]
        if (item[0] == item[1]):
            del combinedOutputs[item]

    types = list(types)
    for item in combinedOutputs.keys():
        combinedOutputs[item]['destination'] = types.index(combinedOutputs[item]['destination'])
        combinedOutputs[item]['source'] = types.index(combinedOutputs[item]['source'])
    if(debug):
        print "after combine strength"
        print combinedOutputs

    return combinedOutputs, types


def doMath(integerList, operator):
    #combine Strength of multiple egdes
    #input integer list,  operator
    #return integer
    #Ying Wu
    operators = ['sum', 'max', 'mean', 'average']
    if len(integerList) == 1:
        return integerList[0]
    #sum
    if(operator == 'sum'):
        return numpy.sum(integerList)
    #max
    elif(operator == 'max'):
        return numpy.max(integerList)
    #mean
    elif(operator == 'mean'):
        return numpy.mean(integerList).round()
    #average
    elif(operator == 'median'):
        return numpy.median(integerList).round()
    else:
        print operator

def neuronID2NeuronType (idTuple, neuronsinfoJson):
    #Ying Wu
    targetID = idTuple[0]
    targetType = getNeuronType(targetID, neuronsinfoJson)
    sourceID = idTuple[1]
    sourceType = getNeuronType(sourceID, neuronsinfoJson)
    return (targetType, sourceType)

def getNeuronType (bodyID, neuronsinfoJson):
    # look up neuron type by neuron body ID
    # reruns neuron type.  If neuron type is not found, use body ID as neuron name
    #Ying Wu
    neuronType = ''
    if str(bodyID) in neuronsinfoJson:
        neuronInfo = neuronsinfoJson[str(bodyID)]
        neuronType = neuronInfo.get("Type")
        if (len(neuronType) == 0):
            neuronType = bodyID
    else:
        neuronType = bodyID

    return neuronType

