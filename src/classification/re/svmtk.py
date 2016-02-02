from __future__ import unicode_literals
import os
from subprocess import Popen, PIPE
import codecs
import sys

import re

import itertools

from classification.re.kernelmodels import KernelModel
# from nltk import WordNetLemmatizer
from nltk.stem.porter import *
from nltk.tree import Tree
import logging

from classification.re import relations
from classification.results import ResultsRE


class SVMTKernel(KernelModel):

    def __init__(self, corpus, modelname="svm_tk_classifier.model"):
        super(SVMTKernel, self).__init__()
        self.modelname = modelname
        self.test_svmtk = []
        self.pids = {}
        # self.lmtzr = WordNetLemmatizer()
        self.stemmer = PorterStemmer()
        self.generate_data(corpus)


    def generate_data(self, corpus):
        if os.path.isfile(self.temp_dir + self.modelname + ".txt"):
            os.remove(self.temp_dir + self.modelname + ".txt")
        xerrors = 0

            #print pairs
        for i, did in enumerate(corpus.documents):
            if "path" in did:
                continue
            doc_lines = []
            pcount = 0
            logging.info("{} {}/{}".format(did, i, len(corpus.documents)))
            for sentence in corpus.documents[did].sentences:
                if 'goldstandard' in sentence.entities.elist:
                    sentence_entities = [entity for entity in sentence.entities.elist["goldstandard"] if entity.type == "event"]
                    # logging.debug("sentence {} has {} entities ({})".format(sentence.sid, len(sentence_entities), len(sentence.entities.elist["goldstandard"])))
                    for pair in itertools.combinations(sentence_entities, 2):
                        sid1 = pair[0].sid
                        sid2 = pair[1].sid
                        pid = did + ".p" + str(pcount)
                        if sid1 != sid2:
                            sentence1 = corpus.documents[did].get_sentence(sid1)
                            tree1 = self.mask_entity(sentence1, Tree.fromstring(sentence1.parsetree), pair[0], "candidate1")
                            sentence2 = corpus.documents[did].get_sentence(sid2)
                            tree2 = self.mask_entity(sentence2, Tree.fromstring(sentence2.parsetree), pair[1], "candidate2")
                            tree = self.join_trees(tree1, tree2)
                        else:
                            sentence1 = corpus.documents[did].get_sentence(sid1)
                            tree = Tree.fromstring(sentence1.parsetree)
                            tree = self.mask_entity(sentence1, tree, pair[0], "candidate1")
                            tree = self.mask_entity(sentence1, tree, pair[1], "candidate2")
                            # if tree[0] != '(':
                            #     tree = '(S (' + tree + ' NN))'
                            #this depends on the version of nlkt

                        tree, found = self.get_path(tree)
                        #if len(docs[sid][ddi.SENTENCE_ENTITIES]) > 20:
                            #print line
                        #    line = "1 |BT| (ROOT (NP (NN candidatedrug) (, ,) (NN candidatedrug))) |ET|"
                        #    xerrors += 1
                        #else:
                        # tree = self.normalize_leaves(tree)
                        line = self.get_svm_train_line(tree, pair)
                        if pair[1].eid not in pair[0].targets:
                            line = '-' + line
                        self.pids[pid] = pair
                        doc_lines.append(line)
                        pcount += 1
            logging.debug("writing {} lines to file...".format(len(doc_lines)))
            with codecs.open(self.temp_dir + self.modelname + ".txt", 'a', "utf-8") as train:
                for l in doc_lines:
                    train.write(l)
        logging.info("wrote {}{}.txt".format(self.temp_dir, self.modelname))

    def train(self, excludesentences=[]):
        if os.path.isfile(self.basedir + self.modelname):
            os.remove(self.basedir + self.modelname)
        svmlightargs = ["./bin/svm-light-TK-1.2/svm-light-TK-1.2.1/svm_learn", "-t", "5",
                              # "-L", "0.6", "-T", "2", "-S", "2", "-g", "1",
                              "-D", "1", "-C", "T", self.temp_dir + self.modelname + ".txt",
                              self.basedir + self.modelname]
        print " ".join(svmlightargs)
        svmlightcall = Popen(svmlightargs,)
                             # stdout = PIPE, stderr = PIPE)
        res = svmlightcall.communicate()
        if not os.path.isfile(self.basedir + self.modelname):
            print "failed training model " + self.basedir + self.modelname
            print res
            sys.exit()

    def load_classifier(self):
        if os.path.isfile(self.basedir + "svm_test_data.txt"):
                os.remove(self.basedir + "svm_test_data.txt")
        if os.path.isfile(self.basedir + "svm_test_output.txt"):
                os.remove(self.basedir + "svm_test_output.txt")
        self.test_svmtk = ["./bin/svm-light-TK-1.2/svm-light-TK-1.2.1/svm_classify",
                              self.temp_dir + self.modelname + ".txt",  self.basedir + self.modelname,
                              self.temp_dir + "svm_test_output.txt"]

    def test(self, model="svm_tk_classifier.model"):
        """
        :param sentence: Sentence object
        :param pairs: dictionary pid => Pair object
        :param pairs_list:
        :param model:
        :param tag:
        :return:
        """

        #docs = use_external_data(docs, excludesentences, dditype)
        #pidlist = pairs.keys()
        total = 0
        #print "tree errors:", xerrors, "total:", total

        svmlightcall = Popen(self.test_svmtk) #, stdout=PIPE, stderr=PIPE)
        res  = svmlightcall.communicate()
        # logging.debug(res[0].split('\n')[-3:])
        #os.system(' '.join(svmtklightargs))
        if not os.path.isfile(self.temp_dir + "svm_test_output.txt"):
            print "something went wrong with SVM-light-TK"
            print res
            sys.exit()

    def get_predictions(self, corpus, resultfile="jsre_results.txt"):
        results = ResultsRE(resultfile)
        with open(self.temp_dir + "svm_test_output.txt", 'r') as out:
            lines = out.readlines()
        # npairs = sum([len(corpus.documents[did].pairs.pairs) for did in corpus.documents])
        # if len(lines) != npairs:
        #    print "check " + "svm_test_output.txt! something is wrong"
        #    sys.exit()
        for ip, pid in enumerate(self.pids):
            score = float(lines[ip])
            # pair = self.get_pair(pid, corpus)
            # results.pairs[pid] = pair
            if float(score) < 0:
                # pair.recognized_by["svmtk"] = -1
                # logging.debug(score)
                pass
            else:
                did = pid.split(".")[0]
                pair = corpus.documents[did].add_relation(self.pids[pid][0], self.pids[pid][1], "tlink", relation=True)
                #pair = self.get_pair(pid, corpus)
                results.pairs[pid] = pair
                pair.recognized_by["svmtk"] = 1
                logging.info("{0.eid}:{0.text} => {1.eid}:{1.text}".format(pair.entities[0],pair.entities[1]))
            #logging.info("{} - {} SST: {}".format(pair.entities[0], pair.entities[0], score))
        results.corpus = corpus

        return results

    def get_path(self, tree, found=0):
        final_tree = ""
        if tree == "candidate1" or tree == "candidate2":
            found += 1
        try:
            tree.label()
        except AttributeError:
            # print "tree:", tree[:5]

        #    print "no label:", dir(tree), tree
            return final_tree + tree + " ", found
        else:
            # Now we know that t.node is defined

            final_tree += '(' + tree.label() + " "
            for child in tree:
                if found < 2:
                    # print "next level:", tree.label()
                    partial_tree, found = self.get_path(child, found)
                    final_tree += partial_tree
                else:
                    break
            final_tree += ')'
        return final_tree, found

    def mask_entity(self, sentence, tree, entity, label):
        """
        Mask the entity names with a label
        :param sentence: sentence object
        :param tree: tree containing the entity
        :param entity: entity object
        :param label: string to replace the original text
        :return: masked tree
        """
        last_text = ""
        match_text = entity.tokens[0].text
        found = False
        entity_token_index = entity.tokens[0].order
        leaves_pos = tree.treepositions('leaves')
        if entity_token_index == 0: # if the entity is the first in the sentence, it's easy
            tree[leaves_pos[0]] = label
            return tree
        if entity_token_index > 0: # otherwise we have to search because the tokenization may be different
            ref_token = sentence.tokens[entity_token_index - 1].text
            # ref_token is used to prevent from matching with the same text but corresponding to a different entity
            # in this case, it is the previous token
            for pos in leaves_pos:
                #exact match case
                if tree[pos] == match_text and (last_text in ref_token or ref_token in last_text):
                    tree[pos] = label
                    return tree
                # partial match - cover tokenization issues
                elif (tree[pos] in match_text or match_text in tree[pos]) and (ref_token in tree[pos] or ref_token in last_text or last_text in ref_token):
                    tree[pos] = label
                    return tree
                last_text = tree[pos]
        # if it was no found, use the next token as reference
        if entity_token_index < sentence.tokens[-1].order and not found:
            for ipos, pos in enumerate(leaves_pos[:-1]):
                ref_token = sentence.tokens[entity_token_index + 1].text
                next_pos = leaves_pos[ipos+1]
                next_text = tree[next_pos]
                if tree[pos] == match_text and (next_text in ref_token or ref_token in next_text):
                    tree[pos] = label
                    return tree
                elif (tree[pos] in match_text or match_text in tree[pos]) and (ref_token in tree[pos] or ref_token in next_text or next_text in ref_token):
                    tree[pos] = label
                    return tree

        logging.debug("entity not found: |{}|{}|{}| in |{}|".format(entity_token_index, ref_token, match_text, str(tree)))
        return tree

    def normalize_leaves(self, tree):
        tree = Tree.fromstring(tree)
        for pos in tree.treepositions('leaves'):
            tree[pos] = self.stemmer.stem(tree[pos]).lower()
        return str(tree).replace("\n", "")

    def get_svm_train_line(self, tree, pair):
        # tree = tree.replace(pair.entities[0].tokens[0].text, 'candidate1')
        # tree = tree.replace(pair.entities[1].tokens[0].text, 'candidate2')
        # TODO: replace other entities
        # tree = re.sub(sid2 + r'\d+', 'otherentity', tree)
        #print "tree2:", tree

        # logging.info("final tree: {}".format(str(tree)))
        #ptree = Tree.parse(tree)
        # leaves = list(tree.pos())
        """lemmaleaves = []
        for t in leaves:
            pos = self.get_wordnet_pos(t[1])
            lemma = lmtzr.lemmatize(t[0].lower(), pos)
            lemmaleaves.append(lemma)"""
        #lemmaleaves = [ for t in leaves)]
        line = '1 '
        line += '|BT|'  + tree
        #bowline = '(BOW (' + ' *)('.join(lemmaleaves) + ' *)) '
        #ptree = Tree.parse(bowline)
        #ptree = ptree.pprint(indent=-1000)
        #bowline = ptree.replace('\n', ' ')
        #bowline = '|BT| ' + bowline
        #if not bowline.count("otherdrug") > 8:
        #    line += bowline
        #else:
            #print "problem with BOW!"
        #line += bowline
        line += '|ET| '

        #i = 1
        #for m in docsp[ddi.PAIR_SSM_VECTOR]:
        #    line += " %s:%s" % (i, m)
        #    i += 1
        #line += " 2:" + str()
        #line += " |EV|"
        line += '\n'
        return line

    def join_trees(self, tree1, tree2):
        ptree = Tree("ROOTROOT", [tree1, tree2])
        return ptree