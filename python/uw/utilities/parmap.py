from abc import abstractmethod
import copy


import numpy as np

class ParameterMapper(object):

    @abstractmethod
    def toexternal(internal): pass

    @abstractmethod
    def tointernal(external): pass

    @abstractmethod
    def dexternaldinternal(external): 
        """ Compute the derivative of the external parametesr
            with respect to the internal parameters
        """
        pass

    def copy(self): return copy.deepcopy(self)

class LinearMapper(ParameterMapper):
    @staticmethod
    def toexternal(internal): return internal

    @staticmethod
    def tointernal(external): return external

    @staticmethod
    def dexternaldinternal(external):
        return 1

class LogMapper(ParameterMapper):
    """ Represent a logarithmic mapping:

            external = 10^internal or internal=log10(internal)
    """
    log_10 = np.log(10)
    @staticmethod
    def toexternal(internal): return 10**internal

    @staticmethod
    def tointernal(external): return np.log10(external)

    @staticmethod
    def dexternaldinternal(external):
        return external*LogMapper.log_10

class LimitMapper(ParameterMapper):
    """ Represents a mapper which limits parametesr between lower and upper

        See section 1.3.1 of "MINUIT User's Guide":

            http://seal.web.cern.ch/seal/documents/minuit/mnusersguide.pdf

        Note, scale doesn't acutally do anything, but is included for
        compatability with gtlike.
    """
    def __init__(self, lower, upper, scale=1):
        self.lower = lower
        self.upper = upper
        self.scale = scale

    def toexternal(self,internal):
        """ Equation 1.2 of "MINUIT User's Guide" """
        return self.lower + ((self.upper-self.lower)/2.0)*(np.sin(internal)+1.0)

    def tointernal(self,external):
        """ Equation 1.1 of "MINUIT User's Guide" """
        return np.arcsin(2.0*(external-self.lower)/(self.upper-self.lower)-1.0)
        
    def dexternaldinternal(self,external):
        return ((self.upper-self.lower)/2.0)*np.cos(self.tointernal(external))

    def __repr__(self):
        return 'LimitMapper(%s,%s,%s)' % (self.lower,self.upper,self.scale)

    def __eq__(self, other):
        """ Previously, equality testing was broken:

                >>> LimitMapper(1,5) == LimitMapper(1,5)
                True
                >>> LimitMapper(1,5) == LimitMapper(1,6)
                False
        """
        return self.lower == other.lower and self.upper == other.upper and self.scale == other.scale

if __name__ == "__main__":
    import doctest
    doctest.testmod()
