import operator
import numpy as np

import os
from scipy.sparse import linalg
from scipy.sparse import csr_matrix
from scipy import sparse
import pickle as pickle

from collections import defaultdict


# create transition matrix from all concepts
def create_transition_matrix(transitions_map, matrix_dimension):
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

    print("creating transition values vector")
    transition_values = np.ones(len(transition_col), dtype=float)
    print("transition values vector for matrix Q created")

    # create sparse matrix Q that contains ones for each transition from A->B and B->A
    print("creating matrix Q")
    matrix_Q = csr_matrix((transition_values, (transition_row, transition_col)), (matrix_dimension, matrix_dimension))
    print(matrix_Q.shape)
    print("matrix Q created")

    # column vector of ones
    print("creating vector I")
    vector_I = np.ones((matrix_dimension, 1), dtype=float)
    print("vector I created")

    # 1D vector that contains the number of transitions in each row
    qi = matrix_Q * vector_I

    for rowN in range(len(qi)):
        value = qi[rowN]
        if value == 0:
            print("Value in row", rowN, "is 0!")

    # create reciprocal matrix and transpose it
    reciprocal_transposed = np.transpose(np.reciprocal(qi))[0, :]

    # create diagonal matrix
    reciprocal_range = range(matrix_dimension)
    print("creating diagonal sparse matrix")
    sparse_diagonal_matrix = csr_matrix((reciprocal_transposed, (reciprocal_range, reciprocal_range)),
                                        (matrix_dimension, matrix_dimension))
    print("diagonal sparse matrix created")

    # get P matrix as a product of Q nad diagonal(inverse(Q * I))
    print("creating P matrix")
    matrix_P = csr_matrix((sparse_diagonal_matrix * matrix_Q), (matrix_dimension, matrix_dimension))
    print("matrix P created")

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
    sparse = csr_matrix((transition_values, (transition_row, transition_col)), (matrix_dimension, matrix_dimension))
    print("matrix J created with shape", sparse.shape)

    return sparse


# normalizes data (0 - 1)
def normalize_data(array):
    return (array - array.min()) / (array.max() - array.min())


# check if value is close enough to given value (used for comparing float values)
def is_close(a, b, rel_tol=1e-07, abs_tol=0.0):
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

    k = len(initial_concepts)  # number of initial concepts

    print("creating P1 matrix from matrix P and matrix J")
    matrix_P1 = csr_matrix(((1 - alfa) * matrix_P) + ((alfa / float(k)) * matrix_J))
    print("matrix P1 created")

    # simulation
    # extract EigenValues and EigenVectors
    print("extracting eigenvalues and eigenvectors")
    [eigenvalues, vectors] = linalg.eigs(matrix_P1.transpose(), k, None, None, 'LM')

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

    # only keep real value
    print("converting vectors to keep only real values")
    resultArray = vectors.real

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

        print("Concept ID", id ,"probability", probability, "word", word, "old ID", old_id)


# method extracts concepts IDs and creates new dictionary from them, if dump doesn't exist yet. if dump exists,
# it just reads it from a dump file
def create_concept_ids(default_concept_file,
                       new_old_id_mapping_dump_path,
                       id_concept_mapping_pickle_dump_path,
                       old_new_id_dict):

    # old_new_id_temp_dict contains the mapping old -> new ID for old concepts that contain transitions
    # so far we have old -> new and new -> old ID dictionary
    new_old_id_dict = {v: k for k, v in old_new_id_dict.items()}

    new_id_to_concept_string_mapping = {}

    if os.path.isfile(id_concept_mapping_pickle_dump_path) and os.path.isfile(new_old_id_mapping_dump_path):

        # try opening concepts file dump and if it doesn't exist, try opening the file and construct dump from it
        print("concept file PICKLE dumps exist")

        print("opening file", new_old_id_mapping_dump_path)
        new_old_id_dict = pickle.load(open(new_old_id_mapping_dump_path, "rb"))
        print("file", new_old_id_mapping_dump_path, "read")

        print("opening file", id_concept_mapping_pickle_dump_path)
        new_id_to_concept_string_mapping = pickle.load(open(id_concept_mapping_pickle_dump_path, "rb"))
        print("file", id_concept_mapping_pickle_dump_path, "read")

    elif os.path.isfile(default_concept_file):
        print("using default concept file path", default_concept_file)
        print("opening concepts file")

        # get maximum value of new ID so far
        counter = int(max(new_old_id_dict, key=int)) + 1
        with open(default_concept_file) as concepts_file:
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

        # close file
        concepts_file.close()
        print("created our own dictionary of old to new and new to old indices and ID to word mappings")

        print("storing our own new-old IDs array to PICKLE dump")
        pickle.dump(new_old_id_dict, open(new_old_id_mapping_dump_path, "wb"))

        print("storing our own dictionary to PICKLE dump")
        pickle.dump(new_id_to_concept_string_mapping, open(id_concept_mapping_pickle_dump_path, "wb"))
    else:
        print("no concept id file or PICKLE dump, cannot proceed")
        exit(1)

    return new_old_id_dict, new_id_to_concept_string_mapping


# method creates concept mapping if it doesn't exist yet. If it does, it just reads if from a dump file
def create_concept_mappings_dict(default_concept_mapping_file,
                                 default_concept_mapping_pickle_dump_path,
                                 default_concept_mapping_pickle_both_transitions_dump_path):
    transition_map = defaultdict(list)  # contains transitions A -> B with old IDs
    both_transitions_map = defaultdict(list)  # contains transitions A -> B and B -> A with old IDs

    # similar to above (but with new IDs)
    new_id_both_transitions_map = defaultdict(list)
    new_id_transitions_map = defaultdict(list)

    if os.path.isfile(default_concept_mapping_pickle_dump_path) and os.path.isfile(
            default_concept_mapping_pickle_both_transitions_dump_path):

        print("concept mapping PICKLE dumps exist")
        print("reading file", default_concept_mapping_pickle_dump_path)
        new_id_transitions_map = pickle.load(open(ID_CONCEPT_MAPPING_PICKLE_DUMP_PATH, "rb"))
        print("file", default_concept_mapping_pickle_dump_path, "read")

        print("reading file", default_concept_mapping_pickle_both_transitions_dump_path)
        new_id_both_transitions_map = pickle.load(open(default_concept_mapping_pickle_both_transitions_dump_path, "rb"))
        print("file", default_concept_mapping_pickle_both_transitions_dump_path, "read")

        print("creating hashmap of old -> new ID")
        # create mapping od old ID to new ID
        old_new_id_dict = {}
        new_id = 0
        for old_id in both_transitions_map:
            old_new_id_dict[old_id] = new_id
            new_id = new_id + 1
        print("hashmap of old -> new ID created")

    elif os.path.isfile(default_concept_mapping_file):
        print("concept file dump doesnt exist. building new one from file", default_concept_mapping_file)

        #  go through each line and build dictionaries for concept transitions
        with open(default_concept_mapping_file) as concept_mappings_file:
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
                    transition_map[old_id].append(value)
                    both_transitions_map[old_id].append(value)
                    both_transitions_map[value].append(old_id)

                    # print progress every 1M
                    if lineN % 1000000 == 0:
                        print(lineN / 1000000)

        # close file
        concept_mappings_file.close()
        print("created concept transition dictionary")

        # remove concepts from dictionaries that don't have any transitions
        print("removing concepts that don't have any transitions")
        remove_keys = []
        for concept in both_transitions_map:
            transitions = both_transitions_map[concept]
            if len(transitions) == 0:
                remove_keys.append(concept)
        for key in remove_keys:
            # remove elements from both dictionaries
            del transition_map[key]
            del both_transitions_map[key]

        print("concepts without transitions and their IDs successfully removed")

        print("creating hashmap of old -> new ID")
        # create mapping od old ID to new ID
        old_new_id_dict = {}
        new_id = 0
        for old_id in both_transitions_map:
            old_new_id_dict[old_id] = new_id
            new_id = new_id + 1
        print("hashmap of old -> new ID created")

        print("creating hashmap of new ID -> transactions with new ID")
        # new mapping for transitions
        for old_id in transition_map:
            # array of transitions but with old ids
            transitions = transition_map[old_id]

            # get new ID for this concept
            new_id = old_new_id_dict[old_id]

            # go through array of transitions
            for transition in transitions:
                # extract new transition ID and append it to the dictionary
                new_transition_id = old_new_id_dict[transition]
                new_id_transitions_map[new_id].append(new_transition_id)

        # new mapping for both transitions
        new_id_both_transitions_map = defaultdict(list)
        for old_id in both_transitions_map:
            # array of transitions but with old ids
            transitions = both_transitions_map[old_id]

            # get new ID for this concept
            new_id = old_new_id_dict[old_id]

            # go through array of transitions
            for transition in transitions:
                # extract new transition ID and append it to the dictionary
                new_transition_id = old_new_id_dict[transition]
                new_id_both_transitions_map[new_id].append(new_transition_id)
        print("hashmap of new ID -> transactions with new ID created")

        print("storing new ID -> transitions hashmap to PICKLE dump")
        pickle.dump(new_id_transitions_map, open(default_concept_mapping_pickle_dump_path, "wb"))
        print("storing new ID -> transitions hashmap to PICKLE dump completed")

        print("storing new ID -> transitions hashmap for both transitions to PICKLE dump")
        pickle.dump(new_id_both_transitions_map, open(default_concept_mapping_pickle_both_transitions_dump_path, "wb"))
        print("storing new ID -> transitions hashmap for both transitions to PICKLE dump completed")
    else:
        print("no concept mapping file or PICKLE dump, cannot proceed")
        exit(2)

    return new_id_transitions_map, new_id_both_transitions_map, old_new_id_dict


# create matrix only if its dump is not stored in the file system yet. If it is, we just read the dump
def create_matrix_P(filePath, both_transitions_map, matrix_dim):
    if os.path.isfile(filePath):
        print("matrix P file path exists")
        print("reading file", filePath)
        matrix = sparse.load_npz(filePath)
        print("file", filePath, "read")
    else:
        matrix = create_transition_matrix(both_transitions_map, matrix_dim)
        print("storing matrix P as sparse npz")
        sparse.save_npz(filePath, matrix)
        print("storing matrix P as sparse npz completed")

    return matrix


if __name__ == '__main__':
    DEFAULT_CONCEPT_FILE = './linkGraph-en-verts.txt'
    DEFAULT_CONCEPT_MAPPING_FILE = './linkGraph-en-edges.txt'
    NEW_OLD_ID_MAPPING_DUMP_PATH = './temp/linkGraph-en-verts-new-old-id-concept-mapping-dump.pkl'
    ID_CONCEPT_MAPPING_PICKLE_DUMP_PATH = './temp/linkGraph-en-verts-id-concept-mapping-dump.pkl'
    DEFAULT_CONCEPT_MAPPING_PICKLE_DUMP_PATH = './temp/linkGraph-en-edges-dump.pkl'
    DEFAULT_CONCEPT_MAPPING_PICKLE_BOTH_TRANSITIONS_DUMP_PATH = './temp/linkGraph-en-edges-both-transitions-dump.pkl'
    MATRIX_P_FILE_PATH = './temp/linkGraph-matrix-P-dump.npz'

    NUMBER_OF_NEW_CONCEPTS = 20
    ALFA = 0.2

    if ALFA < 0 or ALFA > 1:
        print("alfa parameter should be between 0 and 1")
        exit(1)

    # read all concept transitions from a file (or a dump) and create a dictionary with modified IDs
    concept_mappings, concept_mappings_both_transitions, old_new_id_temp_dict = create_concept_mappings_dict(
        DEFAULT_CONCEPT_MAPPING_FILE,
        DEFAULT_CONCEPT_MAPPING_PICKLE_DUMP_PATH,
        DEFAULT_CONCEPT_MAPPING_PICKLE_BOTH_TRANSITIONS_DUMP_PATH)

    # # indices_array is a 1D array where position presents index (new ID) and value presents old ID value
    new_old_idx_map, id_str_concept_map = create_concept_ids(
        DEFAULT_CONCEPT_FILE,
        NEW_OLD_ID_MAPPING_DUMP_PATH,
        ID_CONCEPT_MAPPING_PICKLE_DUMP_PATH,
        old_new_id_temp_dict)

    # matrix dimension is the length of all transitions
    matrix_dimension = len(concept_mappings_both_transitions)

    # TODO check with csc matrix if its faster, because matrix P doesnt need to be transponated

    # create transition matrix
    matrix_P = create_matrix_P(MATRIX_P_FILE_PATH, concept_mappings_both_transitions, matrix_dimension)
    print("matrix P shape", matrix_P.shape)

    # TODO create parser for initial concepts
    initial_concepts = [50, 100, 231, 3523, 1123, 56234, 1231, 1231, 3432, 131, 53245, 544, 11, 1, 111, 555, 1231, 5267, 14676, 352355, 2141, 5235, 56325]

    calc_neighbourhood(matrix_dimension,
                       concept_mappings,
                       initial_concepts,
                       matrix_P,
                       id_str_concept_map,
                       new_old_idx_map,
                       NUMBER_OF_NEW_CONCEPTS,
                       ALFA)
