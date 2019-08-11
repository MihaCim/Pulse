import operator
import numpy as np

import time
import os
import sys
import signal
import subprocess
import psutil
from scipy.sparse import linalg
from scipy.sparse import csc_matrix
from scipy import sparse

import json as json

from collections import defaultdict
from db import Database


def create_transition_matrix(transitions_map, matrix_dimension):
    # create transition matrix from all concepts
    print("creating transition matrix P of dimension", matrix_dimension, "x", matrix_dimension)
    transition_row = []
    transition_col = []

    # go through concept mappings
    id = 0
    counter = 0
    for concept_idx in transitions_map:
        transitions = transitions_map[concept_idx]
        transition_row.extend([concept_idx] * len(transitions))
        transition_col.extend(transitions)

        id = id + len(transitions)
        counter = counter + 1
        if counter % 100000 == 0:
            print("at counter", counter, "current ID is", id)

    # remove transition map from memory
    del transitions_map

    print("creating transition values vector")
    transition_values = np.ones(len(transition_col), dtype=float)
    print("transition values vector for matrix Q created")

    # create sparse matrix Q that contains ones for each transition from A->B and B->A
    print("creating matrix Q")
    matrix_Q = csc_matrix((transition_values, (transition_row, transition_col)), (matrix_dimension, matrix_dimension))
    print(matrix_Q.shape)
    print("matrix Q created")

    # remove arrays for creating matrix Q from memory
    del transition_values
    del transition_row
    del transition_col

    # column vector of ones
    print("creating vector I")
    vector_I = np.ones((matrix_dimension, 1), dtype=float)
    print("vector I created")

    # 1D vector that contains the number of transitions in each row
    qi = matrix_Q * vector_I

    # remove vector I from memory
    del vector_I

    # create reciprocal matrix and transpose it
    reciprocal_transposed = np.transpose(np.reciprocal(qi))[0, :]

    # remove vector qi
    del qi

    # create diagonal matrix
    reciprocal_range = range(matrix_dimension)
    print("creating diagonal sparse matrix")
    sparse_diagonal_matrix = csc_matrix((reciprocal_transposed, (reciprocal_range, reciprocal_range)),
                                        (matrix_dimension, matrix_dimension))
    print("diagonal sparse matrix created")

    # remove properties of reciprocal matrix
    del reciprocal_range
    del reciprocal_transposed

    # get P matrix as a product of Q nad diagonal(inverse(Q * I))
    print("creating P matrix")
    matrix_P = csc_matrix((sparse_diagonal_matrix * matrix_Q), (matrix_dimension, matrix_dimension))
    print("matrix P created")

    # remove sparse diagonal matrix
    del sparse_diagonal_matrix
    del matrix_Q

    return matrix_P


# creates transition matrix from initial concepts
def create_initial_concept_transition_matrix(initial_concepts, all_concepts, matrix_dimension):
    print("creating initial concept transition matrix J")
    transition_row = []
    transition_col = []

    # go through every initial concept
    for colN in initial_concepts:
        transition_col.extend([colN] * len(all_concepts))
        transition_row.extend(all_concepts)

    print("creating transition values vector")
    transition_values = np.ones(len(transition_col), dtype=float)
    print("transition values vector created")

    # create sparse matrix
    sparse = csc_matrix((transition_values, (transition_row, transition_col)), (matrix_dimension, matrix_dimension))
    print("matrix J created with shape", sparse.shape)

    # remove values for sparse matrix
    del transition_col
    del transition_row
    del transition_values

    return sparse


# normalizes data (0 - 1)
def normalize_data(array):
    return (array - array.min()) / (array.max() - array.min())


# check if value is close enough to given value (used for comparing float values)
def is_close(a, b, rel_tol=1e-03, abs_tol=0.0):
    return abs(a - b) <= max(rel_tol * max(abs(a), abs(b)), abs_tol)


# method calculates neighbourhood based on concept mappings and initial concepts
def calc_neighbourhood(matrix_dimension,
                       concept_mappings,
                       initial_concepts,
                       matrix_P,
                       id_string_map,
                       new_old_index_mapping,
                       number_of_wanted_concepts,
                       alfa):
    # create matrix that contains transition probabilities from each concept back to initial concept
    matrix_J = create_initial_concept_transition_matrix(initial_concepts, concept_mappings, matrix_dimension)

    print("creating P1 matrix from matrix P and matrix J")
    matrix_P1 = csc_matrix(((1 - alfa) * matrix_P) + ((alfa / float(len(initial_concepts))) * matrix_J))
    print("matrix P1 created")

    # remove matrix J and P from memory
    del matrix_J
    del matrix_P

    print("Transposing matrix P1...")
    transposed = matrix_P1.transpose()
    print("Transposing matrix P1 completed")

    # simulation
    # extract EigenValues and EigenVectors
    print("extracting eigenvalues and eigenvectors")
    [eigenvalues, vectors] = linalg.eigs(transposed, k=1)

    print("eigenvalues", eigenvalues)
    print("eigenvectors", vectors)

    # extract only the column where EigenValue is 1.0
    print("extracting column of eigenvectors where eigenvalue is 1")
    result_array_idx = -1
    for eigenValueIdx in range(len(eigenvalues)):
        value = eigenvalues[eigenValueIdx].real

        if is_close(value, 1.0):
            result_array_idx = eigenValueIdx
            break
    if result_array_idx == -1:
        print("No EigenValue 1.0 in received eigenvalues. Exiting program...")
        exit(3)
    print("extracted eigenvectors successfully")

    # remove eigen values from memory
    del eigenvalues

    # only keep real value
    print("converting vectors to keep only real values")
    resultArray = vectors.real

    # remove eigen vectors from memory
    del vectors

    # normalize data from column with index result_array_idx because that column represents our results
    print("normalizing data")
    normalizedArray = normalize_data(resultArray.T[result_array_idx])
    print("data normalized")

    print("creating array of similar concepts")
    similar_concepts = {}
    for concept_id in range(len(normalizedArray.T)):
        value = normalizedArray.T[concept_id]

        # if ID is not the same as initial concept, extract the value
        if concept_id not in initial_concepts:
            similar_concepts[concept_id] = value

    # sort descending - most similar concept is the highest
    print("sorting array of similar concepts descdending by probability")
    sorted_similar_concepts = sorted(similar_concepts.items(), key=operator.itemgetter(1), reverse=True)

    # extract as many concepts as wanted by variable number_of_wanted_concepts
    extracted_concepts = sorted_similar_concepts[:number_of_wanted_concepts]

    # print result
    for final_concept in extracted_concepts:
        id = final_concept[0]
        probability = final_concept[1]
        old_id = new_old_index_mapping[id]
        word = id_string_map[id]

        print("Concept ID", id, "probability", probability, "word", word, "old ID", old_id)

    # TODO store result to the database


# method extracts concepts IDs and creates new dictionary from them, if dump doesn't exist yet. if dump exists,
# it just reads it from a dump file
def create_concept_ids(default_concept_file,
                       new_old_id_mapping_dump_path,
                       id_concept_mapping_json_dump_path,
                       old_new_id_dict):
    new_old_id_dict = {}
    if len(old_new_id_dict) != 0:
        # old_new_id_temp_dict contains the mapping old -> new ID for old concepts that contain transitions
        # so far we have old -> new and new -> old ID dictionary
        new_old_id_dict = {v: k for k, v in old_new_id_dict.items()}

    new_id_to_concept_string_mapping = {}

    if os.path.isfile(id_concept_mapping_json_dump_path) and os.path.isfile(new_old_id_mapping_dump_path):

        # try opening concepts file dump and if it doesn't exist, try opening the file and construct dump from it
        print("concept file json dumps exist")

        print("opening file", new_old_id_mapping_dump_path)
        with open(new_old_id_mapping_dump_path, 'r') as fp1:
            new_old_dict_load = json.load(fp1)
        new_old_id_dict = {int(old_key): val for old_key, val in
                           new_old_dict_load.items()}  # convert string keys to integers
        print("file", new_old_id_mapping_dump_path, "read")

        print("opening file", id_concept_mapping_json_dump_path)
        with open(id_concept_mapping_json_dump_path, 'r') as fp2:
            new_id_to_concept_string_load = json.load(fp2)
        new_id_to_concept_string_mapping = {int(old_key): val for old_key, val in
                                            new_id_to_concept_string_load.items()}  # convert string keys to integers
        print("file", id_concept_mapping_json_dump_path, "read")

    elif os.path.isfile(default_concept_file):
        print("using default concept file path", default_concept_file)
        print("opening concepts file")

        # get maximum value of new ID so far if dictionary has any fields
        if len(new_old_id_dict) == 0:
            counter = 0  # start from the beginning
        else:
            counter = int(max(new_old_id_dict, key=int)) + 1  # continue where we left off

        with open(default_concept_file, 'r') as concepts_file:
            for lineN, line in enumerate(concepts_file):
                line = line.strip()
                split = line.split("\t")

                if len(split) < 3:
                    print("Skipping line because it doesn't have at least 3 columns...")
                else:
                    if not split[0].isdigit():
                        continue

                    # append each element after previous one. indices are new IDs, values are old IDs
                    old_id = int(split[0])

                    # if its not in old -> new dictionary, its not in new -> old dictionary
                    new_id = counter
                    if old_id not in old_new_id_dict.keys():
                        # and new key to old -> new and new old ID to new -> old, increment counter
                        old_new_id_dict[old_id] = counter
                        new_old_id_dict[counter] = old_id
                        counter = counter + 1
                    else:
                        new_id = old_new_id_dict[old_id]

                    # get new ID
                    new_id_to_concept_string_mapping[new_id] = split[2]

                    # print progress every 10M
                    if lineN % 1000000 == 0:
                        print(lineN / 1000000)
        print("created our own dictionary of old to new and new to old indices and ID to word mappings")

        # remove old -> new dictionary from memory
        del old_new_id_dict

        print("storing our own new-old IDs array to json dump")
        with open(new_old_id_mapping_dump_path, 'w') as fp1:
            json.dump(new_old_id_dict, fp1)

        print("storing our own dictionary to json dump")
        with open(id_concept_mapping_json_dump_path, 'w') as fp2:
            json.dump(new_id_to_concept_string_mapping, fp2)
    else:
        print("no concept id file or json dump, cannot proceed")
        exit(1)

    return new_old_id_dict, new_id_to_concept_string_mapping


# method creates concept mapping if it doesn't exist yet. If it does, it just reads if from a dump file
def create_concept_mappings_dict(default_concept_mapping_file,
                                 default_concept_mapping_json_both_dump_path,
                                 should_use_both_transitions):
    concept_transition_map = defaultdict(
        list)  # contains transitions A -> B (and B -> A with old IDs if should_use_both_transitions flag is set)

    # similar to above (but with new IDs)
    new_id_concept_transition_map = defaultdict(list)

    if os.path.isfile(default_concept_mapping_json_both_dump_path):

        print("concept mapping json dumps exist")
        print("reading file", default_concept_mapping_json_both_dump_path)
        with open(default_concept_mapping_json_both_dump_path, 'r') as fp2:
            new_id_mapping_load = json.load(fp2)
        new_id_concept_transition_map = {int(old_key): val for old_key, val in
                                         new_id_mapping_load.items()}  # convert string keys to integers
        print("file", default_concept_mapping_json_both_dump_path, "read")

        print("creating hashmap of old -> new ID")
        # create mapping od old ID to new ID
        old_new_id_dict = {}
        new_id = 0
        for old_id in new_id_concept_transition_map:
            old_new_id_dict[old_id] = new_id
            new_id = new_id + 1
        print("hashmap of old -> new ID created")

    elif os.path.isfile(default_concept_mapping_file):
        print("concept file dump doesnt exist. building new one from file", default_concept_mapping_file)

        #  go through each line and build dictionaries for concept transitions
        with open(default_concept_mapping_file, 'r') as concept_mappings_file:
            for lineN, line in enumerate(concept_mappings_file):
                line = line.strip()
                split = line.split("\t")

                if len(split) < 2:
                    print("Skipping line because it doesn't have at least 2 columns (concept ID and connection)")
                else:
                    # skip a line if it doesnt contain a number
                    if not split[0].isdigit() or not split[1].isdigit():
                        continue

                    # declare two variables for start node ID and end node ID
                    old_id = int(split[0])
                    value = int(split[1])

                    # if key already exists in a dict, it appends value to it instead of overriding it
                    concept_transition_map[old_id].append(value)

                    # if this flag is set, old_id points to value and value also points to old_id
                    if should_use_both_transitions:
                        concept_transition_map[value].append(old_id)

                    # print progress every 1M
                    if lineN % 10000000 == 0:
                        print(lineN / 1000000)
        print("created concept transition dictionary")

        # remove concepts from dictionaries that don't have any transitions
        print("removing concepts that don't have any transitions")
        remove_keys = []
        for concept in concept_transition_map:
            transitions = concept_transition_map[concept]
            if len(transitions) == 0:
                remove_keys.append(concept)
        for key in remove_keys:
            # remove elements from both dictionaries
            del concept_transition_map[key]

        print("concepts without transitions and their IDs successfully removed")

        print("creating hashmap of old -> new ID")
        # create mapping od old ID to new ID
        old_new_id_dict = {}
        new_id = 0
        for old_id in concept_transition_map:
            old_new_id_dict[old_id] = new_id
            new_id = new_id + 1
        print("hashmap of old -> new ID created")

        print("creating hashmap of new ID -> transactions with new ID")

        # new mapping for both transitions
        new_id_concept_transition_map = defaultdict(list)
        id = 0
        counter = 0
        for old_id in concept_transition_map:
            # array of transitions but with old ids
            transitions = concept_transition_map[old_id]

            # get new ID for this concept
            new_id = old_new_id_dict[old_id]

            # go through array of transitions
            for transition in transitions:
                # extract new transition ID and append it to the dictionary
                new_transition_id = old_new_id_dict[transition]
                new_id_concept_transition_map[new_id].append(new_transition_id)

                id = id + len(transitions)
                counter = counter + 1
                if counter % 10000000 == 0:
                    print("at counter", counter, "current ID is", id)

        print("hashmap of new ID -> transactions with new ID created")

        # remove transition map from memory
        del concept_transition_map

        print("storing new ID -> transitions hashmap for both transitions to json dump")
        with open(default_concept_mapping_json_both_dump_path, 'w') as fp2:
            json.dump(new_id_concept_transition_map, fp2)
        print("storing new ID -> transitions hashmap for both transitions to json dump completed")
    else:
        print("no concept mapping file or json dump, cannot proceed")
        exit(2)

    return new_id_concept_transition_map, old_new_id_dict


def init_dictionaries():
    default_concept_file = './linkGraph-en-verts.txt'
    default_concept_mapping_file = './linkGraph-en-edges.txt'
    new_old_id_mapping_dump_path = './temp/linkGraph-en-verts-new-old-id-concept-mapping-dump.json'
    id_concept_mapping_json_dump_path = './temp/linkGraph-en-verts-id-concept-mapping-dump.json'
    default_concept_mapping_json_dump_path = './temp/linkGraph-en-edges-dump.json'
    default_concept_mapping_json_both_transitions_dump_path = './temp/linkGraph-en-edges-both-transitions-dump.json'
    matrix_p_file_path = './temp/linkGraph-matrix-P-dump.npz'

    # initial values
    old_new_id_temp_dict = {}

    # check if matrix P exists. If it does, we don't need to calculate concept mappings for both transitions,
    # if it doesn't, we need to calculate it
    if os.path.isfile(matrix_p_file_path):
        print("matrix P file path exists")
        print("reading file", matrix_p_file_path)
        matrix_P = sparse.load_npz(matrix_p_file_path)
        print("file", matrix_p_file_path, "read")
    else:
        # read all concept transitions from a file (or a dump) and create a dictionary with modified IDs
        concept_mappings_both_transitions, old_new_id_temp_dict = create_concept_mappings_dict(
            default_concept_mapping_file,
            default_concept_mapping_json_both_transitions_dump_path, True)

        # matrix dimension is the length of all transitions
        matrix_dimension = len(concept_mappings_both_transitions)

        # create matrix from both transitions maps
        matrix_P = create_transition_matrix(concept_mappings_both_transitions, matrix_dimension)
        print("storing matrix P as sparse npz")
        sparse.save_npz(matrix_p_file_path, matrix_P)
        print("storing matrix P as sparse npz completed")

        del concept_mappings_both_transitions

    # indices_array is a 1D array where position presents index (new ID) and value presents old ID value
    new_old_idx_map, id_str_concept_map = create_concept_ids(
        default_concept_file,
        new_old_id_mapping_dump_path,
        id_concept_mapping_json_dump_path,
        old_new_id_temp_dict)

    del old_new_id_temp_dict

    # create concept mappings
    concept_mappings = create_concept_mappings_dict(
        default_concept_mapping_file,
        default_concept_mapping_json_dump_path,
        False)

    return concept_mappings, matrix_P, id_str_concept_map, new_old_idx_map


def handler(signum, frame):
    # catch signal for abort/kill application and also kill API process
    print('Signal handler called with signal', signum, ', killing api process and exiting application')
    if apiProcess is not None:
        kill(apiProcess.pid)
    sys.exit()


def kill(proc_pid):
    # kills process using psutil package
    process = psutil.Process(proc_pid)
    for proc in process.children(recursive=True):
        proc.kill()
    process.kill()


if __name__ == '__main__':
    ##################################################################################
    #                       DATABASE AND API INITIALIZATION
    ##################################################################################
    print("Start : %s" % time.ctime())

    # get instance of database connection
    db_name = "concepts_db"
    database = Database(db_name)
    database.create_database(db_name)
    # database.drop_table("concepts")
    # create table if it doesn't exist
    database.create_table("CREATE TABLE IF NOT EXISTS concepts ("
                          "id serial PRIMARY KEY NOT NULL, "
                          "timestamp BIGINT NOT NULL, "
                          "alpha REAL NOT NULL,"
                          "concepts REAL NOT NULL,"
                          "result VARCHAR)")

    # TODO insert
    database.execute("INSERT INTO concepts(id, timestamp, alpha, concepts) VALUES(DEFAULT, 431234124, 0.2, 10)")
    database.execute("INSERT INTO concepts(id, timestamp, alpha, concepts) VALUES(DEFAULT, 523523, 0.2, 0.5)")
    result = database.query("SELECT * FROM concepts")
    print(result)

    # TODO select
    result = database.query("SELECT * FROM concepts WHERE id = %s", (9,))
    print(result)

    # TODO update
    database.execute("UPDATE concepts set result = %s where id = %s", ("testtest", 6))
    result = database.query("SELECT * FROM concepts WHERE id = %s", (6,))
    print(result)

    # TODO clean database
    database.execute("DELETE FROM concepts WHERE timestamp < %s", (999999,))
    result = database.query("SELECT * FROM concepts")
    print(result)

    # start API as subprocess
    apiProcess = subprocess.Popen(["python", "api.py"])

    # setup handler that will kill api if signal for abort/kill arrives (ctrl+c, ctrl+z)
    signal.signal(signal.SIGABRT, handler)
    signal.signal(signal.SIGINT, handler)
    signal.signal(signal.SIGTSTP, handler)

    ##################################################################################
    #                              SCRIPT INITIALIZATION
    ##################################################################################

    # init dictionaries needed for API and concepts needed for API
    concept_mappings, matrix_P, id_str_concept_map, new_old_idx_map = init_dictionaries()

    # calculate matrix dimension based on concept mappings length
    matrix_dimension = len(concept_mappings)

    # initial concepts will be given as array of strings API parameter
    # TODO map strings to concept IDs
    initial_concepts = [9000, 1000, 1500, 2000, 2500, 3000, 3500, 4000, 4500, 5000, 1000, 54324, 11241, 11100, 10101]

    print("Got initial concepts at : %s" % time.ctime())

    ##################################################################################
    #                            PROCESSING OF REQUESTS
    ##################################################################################

    while True:



        # TODO
        # keep checking whether anything is to be processed in the database and
        # if parameter is a percent, calculate it to the number of new concepts
        # alfa and number of new concepts will be given as API parameter
        NUMBER_OF_NEW_CONCEPTS = 20
        ALFA = 0.2
        request_id = 1000

        if ALFA < 0 or ALFA > 1:
            print("alfa parameter should be between 0 and 1")
            exit(1)

        # calculate neighbourhood and store result into database
        calc_neighbourhood(matrix_dimension,
                           concept_mappings,
                           initial_concepts,
                           matrix_P,
                           id_str_concept_map,
                           new_old_idx_map,
                           NUMBER_OF_NEW_CONCEPTS,
                           ALFA)

        time.sleep(10)
