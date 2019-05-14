# I want to move this to it's own module but haven't had the time yet.

from ..tinyhouse import Pedigree


import numba
from numba import jit, int8, int64, boolean, deferred_type, optional, jitclass, float32, double
from collections import OrderedDict
import numpy as np

class AlphaImputeIndividual(Pedigree.Individual):
    def __init__(self, idx, idn):
        super().__init__(idx, idn)

        self.segregation = None
        self.originalGenotypes = None
        self.anterior = None
        self.penetrance = None
        self.posterior = None

    def setupIndividual(self):
        nLoci = len(self.genotypes)
        self.segregation = (np.full(nLoci, 9, dtype = np.int8), np.full(nLoci, 9, dtype = np.int8))
        self.originalGenotypes = self.genotypes.copy()

        self.anterior = np.full((4, nLoci), 1, dtype = np.int8) # There's probably some space saving format we could do here... 
        self.penetrance = np.full((4, nLoci), 1, dtype = np.int8) 
        self.posterior = np.full((4, nLoci), 1, dtype = np.int8)

    def toJit(self):
        """Returns a just in time version of itself with the same idn and holders for haplotypes and genotypes"""

        if self.genotypes is None or self.haplotypes is None:
            raise ValueError("In order to just in time an Individual, both genotypes and haplotypes need to be not None")
        nLoci = len(self.genotypes) # self.genotypes will always be not None (otherwise error will be raised above).
        return jit_Individual(self.idn, self.genotypes, self.haplotypes, self.segregation, self.anterior, self.penetrance, self.posterior, nLoci)

    def setGenotypesPenetrance(self):
        self.toJit().setGenotypesFromPeelingData(False, True, False)

    def setGenotypesAll(self):
        self.toJit().setGenotypesFromPeelingData(True, True, True)

    def setGenotypesAnterior(self):
        self.toJit().setGenotypesFromPeelingData(True, True, False)

    def setGenotypesPosterior(self):
        self.toJit().setGenotypesFromPeelingData(False, True, True)

    def clearGenotypes(self):
        self.genotypes[:] = 9
        self.haplotypes[0][:] = 9
        self.haplotypes[1][:] = 9

spec = OrderedDict()
spec['idn'] = int64
spec['nLoci'] = int64
spec['genotypes'] = int8[:]
# Haplotypes and reads are a tuple of int8 and int64.
spec['haplotypes'] = numba.typeof((np.array([0, 1], dtype = np.int8), np.array([0], dtype = np.int8)))
spec['segregation'] = numba.typeof((np.array([0, 1], dtype = np.int8), np.array([0], dtype = np.int8)))

spec['anterior'] = int8[:,:]
spec['penetrance'] = int8[:,:]
spec['posterior'] = int8[:,:]



@jitclass(spec)
class jit_Individual(object):
    def __init__(self, idn, genotypes, haplotypes, segregation, anterior, penetrance, posterior, nLoci):
        self.idn = idn

        self.genotypes = genotypes
        self.haplotypes = haplotypes
        self.segregation = segregation

        self.anterior = anterior
        self.penetrance = penetrance
        self.posterior = posterior

        self.nLoci = nLoci

    def setValueFromGenotypes(self, mat):
        nLoci = self.nLoci
        mat[:,:] = 1
        for i in range(nLoci):
            g = self.genotypes[i]
            
            if g == 0:
                mat[0,i] = 1
                mat[1,i] = 0
                mat[2,i] = 0
                mat[3,i] = 0
            if g == 1:
                mat[0,i] = 0
                mat[1,i] = 1
                mat[2,i] = 1
                mat[3,i] = 0

            if g == 2:
                mat[0,i] = 0
                mat[1,i] = 0
                mat[2,i] = 0
                mat[3,i] = 1

            # Handle haplotypes by rulling out genotype states
            if self.haplotypes[0][i] == 0:
                mat[2,i] = 0
                mat[3,i] = 0

            if self.haplotypes[0][i] == 1:
                mat[0,i] = 0
                mat[1,i] = 0

            if self.haplotypes[1][i] == 0:
                mat[1,i] = 0
                mat[3,i] = 0

            if self.haplotypes[1][i] == 1:
                mat[0,i] = 0
                mat[2,i] = 0



    def setGenotypesFromPeelingData(self, useAnterior = False, usePenetrance = False, usePosterior = False):
        nLoci = self.nLoci

        finalGenotypes = np.full((4, nLoci), 1, dtype = np.int8) 
        for i in range(nLoci):
            for j in range(4):
                if useAnterior:
                    if self.anterior[j, i] == 0 :
                        finalGenotypes[j, i] = 0
                if usePosterior:
                    if self.posterior[j, i] == 0 :
                        finalGenotypes[j, i] = 0
                if usePenetrance:
                    if self.penetrance[j, i] == 0 :
                        finalGenotypes[j, i] = 0


            g = finalGenotypes[:,i]
            count = g[0] + g[1] + g[2] + g[3]
            if count == 0:
                for j in range(4):
                    finalGenotypes[j, i] = self.penetrance[j, i] # In places where no consensus happens, default to anterior. 
        # Final genotypes represents a set of genotype probabilities. There are... 16 options, 8 of which we care about.

        for i in range(nLoci):
            g = finalGenotypes[:,i]
            
            count = g[0] + g[1] + g[2] + g[3]
            # This all feels kinda messy, but it works?
            # Only one genotype option: genotype + haplotype known.
            if count == 1:
                if g[0] == 1 :
                    self.genotypes[i] = 0
                    self.haplotypes[0][i] = 0
                    self.haplotypes[1][i] = 0
                
                elif g[1] == 1:
                    self.genotypes[i] = 1
                    self.haplotypes[0][i] = 0
                    self.haplotypes[1][i] = 1

                elif g[2] == 1:
                    self.genotypes[i] = 1
                    self.haplotypes[0][i] = 1
                    self.haplotypes[1][i] = 0

                elif g[3] == 1:
                    self.genotypes[i] = 2
                    self.haplotypes[0][i] = 1
                    self.haplotypes[1][i] = 1

            elif count == 2:
                # We generally can call one haplotype here, but probably not both.                
                self.genotypes[i] = 9
                if g[0] == 1 and g[1] == 1:
                    self.haplotypes[0][i] = 0
                    self.haplotypes[1][i] = 9
                if g[2] == 1 and g[3] == 1:
                    self.haplotypes[0][i] = 1
                    self.haplotypes[1][i] = 9
                
                if g[0] == 1 and g[2] == 1:
                    self.haplotypes[0][i] = 9
                    self.haplotypes[1][i] = 0
                if g[1] == 1 and g[3] == 1:
                    self.haplotypes[0][i] = 9
                    self.haplotypes[1][i] = 1

                if g[1] == 1 and g[2] == 1:
                    # We can call the genotype here, but not the haplotype. 
                    # There's another state like this that we are going to ignore.
                    self.genotypes[i] = 1 
                    self.haplotypes[0][i] = 9
                    self.haplotypes[1][i] = 9
            else:
                # if count == 0: 
                    # print("0 state")
                    # print(self.anterior[:,i], self.posterior[:,i], self.penetrance[:,i])
                self.genotypes[i] = 9
                self.haplotypes[0][i] = 9
                self.haplotypes[1][i] = 9


