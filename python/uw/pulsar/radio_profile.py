
import numpy as np
import os

class Profile(object):
    """ Encapsulate the profile with its identifying information."""

    """
    defaults = (
        ('ncol',2,'The column containing the Stokes I parameter.'),
        ('freq',1.4,'The observing frequency in GHz.')
    )
    """

    #@keyword_options.decorate(defaults)
    def __init__(self,profile,jname=None,**kwargs):
        """ profile -- the (ASCII) radio profile file """
        #keyword_options.process(self,kwargs)
        self.pfile = profile
        self.jname = jname
        self.obs = None

        ### default values -- will be updated automatically for profile type
        self.ncol = 2 # the ascii column with the Stokes I parameter (from 1)
        self.freq = 1.4 # observing freq in GHz
        self.fidpt = 0 # fiducial point of TOAs relative to profile
        ###

        self._process()

    def _process(self):
        """ Determine properties of profiles. """
        #1 -- if file name ends with '.asc', it's a Nancay profile
        pfile = os.path.split(self.pfile)[-1]
        if pfile.endswith('.asc'):
            self._process_nan()
        #2 -- JBO/PKS in the file name are giveaways
        elif 'JBO' in pfile:
            self._process_jbo()
        elif 'PKS' in pfile:
            self._process_pks()
        #3 -- one instance of DFB2 (parkes)
        elif 'PDFB2' in pfile:
            self._process_pks()
        #4 -- a Camilo/GBT style bestprof file
        elif pfile.endswith('bestprof'):
            self._process_bestprof()
        else:
            raise ValueError('Could not discern type of %s'%pfile)
        self.fitpt = self.fidpt % 1 # just in case

    def _process_nan(self):
        """ Nancay profiles properties:
            oo 1st harmonic convention (approximate)
            oo 1.4 GHz observing frequency
            oo fidicual_point specified in comments 
            oo amplitude given by 2nd column
        """
        self.obs = 'NAN'
        for line in file(self.pfile):
            if 'fiducial_point' in line: break
        line = line.strip().split()[-2]
        self.fidpt = float(line)

    def _process_jbo(self):
        """ Jodrell Bank profiles properties:
            oo 1.4 GHz observing frequency
            oo fidicual_point specified in comments (first line; typically 0)
            oo amplitude given by 2nd column
        """
        self.obs = 'JBO'
        self.fidpt = float((file(self.pfile).next()).split()[-1])
        #if self.fidpt != 0:
            #print 'Found a JBO profile (%s) without fidpt=0 (at %.4f)'%(self.pfile,self.fidpt)

    def _process_pks(self):
        """ Parkes profiles properties:
            oo 1.4 GHz observing frequency
            oo fidicual_point is always 0
            oo amplitude given by 2nd column
        """
        # nothing to do for PKS
        self.obs = 'PKS'

    def _process_bestprof(self):
        """ 'bestprof' profiles properties:
            oo follow first harmonic conventions
            oo arbitrary observing frequency, typically 1.4
            oo arbitrary observatory, typically PKS
            oo amplitude given by 2nd column
        """
        # look for information encoded in .profile
        comments = [line for line in file(self.pfile) if line[0] == '#']
        for comment in comments:
            if 'obs' in comment:
                self.obs = comment.split()[-1]
            elif 'freq' in comment:
                self.freq = comment.split()[-1]
        # otherwise, assume defaults
        self._first_harmonic()

    def _first_harmonic(self):
        """ Compute the zero of phase of a radio profile by determining the 
            position of the fundamental peak."""
        TWOPI = 2*np.pi
        self.fidpt = 0
        vals = self.get_amplitudes()
        ph = np.linspace(0,TWOPI,len(vals)+1)[:-1] # LEFT bin edges
        a1 = (np.sin(ph)*vals).sum()
        a2 = (np.cos(ph)*vals).sum()
        self.fidpt = np.arctan2(a1,a2)/TWOPI

    def get_amplitudes(self,align_to_peak=False,bin_goal=None):
        """ Produce an ordered list of amplitudes as a function of phase,
            rotated such that the fiducial point is at 0.  The profile 
            is re-binned with linear interpolation.
            
            bin_goal [None] -- will attempt to average the light curve to
                between between bin_goal and 2xbin_goal bins"""
        try:
            phases = np.loadtxt(self.pfile,comments='#')[:,self.ncol-1]
        except IndexError:
            phases = np.loadtxt(self.pfile,comments='#')
        if len(phases.shape) > 1:
            raise ValueError('Could not read profile values.')

        if self.fidpt != 0:
            x0 = np.linspace(0,1,len(phases)+1)[:-1]
            x = np.concatenate((x0,x0+1,[2]))
            y = np.concatenate((phases,phases,[phases[0]]))
            rvals = np.interp(x0+self.fidpt,x,y)
        else:
            rvals = phases
        if bin_goal > 0:
            if len(rvals) % 2 > 0: 
                rvals = np.append(rvals,rvals[0])
            while len(rvals) > bin_goal:
                rvals = (rvals[:-1:2]+rvals[1::2])/2
        return rvals