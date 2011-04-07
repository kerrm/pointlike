import skymaps as s
import pylab as py
import numpy as np
from uw.stacklike.stacklike import *
from uw.stacklike.angularmodels import *
from uw.utilities.minuit import Minuit
from uw.like.pycaldb import CALDBManager
from uw.like.pypsf import CALDBPsf
from uw.like.quadform import QuadForm,Ellipse
import scipy.optimize as so
import scipy.misc as sm
import os as os
import copy as cp
import glob as glob
import time as t
from ROOT import Double


####################### PSR file naming conventions ######################
#
#    pulsar source list text file:
#
#    (psr).txt
# name     ra     dec
# PSR0835-4510    128.8357   -45.1863
#
#   ft1 files:
#   (psr)on-ft1.fits
#   (psr)off-ft1.fits
#

##############################################  Namespace Defaults #############################################

pulsdir = '/phys/groups/tev/scratch1/users/Fermi/mar0/data/pulsar/'               #directory with pulsar ft1 data
agndir = '/phys/groups/tev/scratch1/users/Fermi/mar0/data/6.3/'                   #directory with agn ft1 data
srcdir = '/phys/users/mar0/sourcelists/'                                          #directory with lists of source locations (name ra dec)
cachedir = '/phys/users/mar0/cache/'
pulsars = [('vela',1.0)]#,('gem',1.0)]                                                          #pulsar sourcelist name 
agnlist = ['agn-psf-study-bright']
irf = 'P6_v8_diff'
rd = 180./np.pi

###############################################  CombinedLike Class ############################################

## Implements the likelihood analysis outlined by Matthew Wood
## available here: http://fermi-ts.phys.washington.edu/pointlike/common/psf_lnl.pdf
class CombinedLike(object):


    ## constructor for Combinedlikelihood class
    #  @param pulsdir pulsar ft1 data directory
    #  @param agndir agn ft1 data directory
    #  @param srcdir sourcelist directory (see Stacklike documentation)
    #  @param pulsars (sourcelist,alpha) names of pulsar list and ratio of on/off pulse
    #  @param agnlist list of agn sources
    #  @param irf intial response function
    def __init__(self,**kwargs):
        self.pulsdir = pulsdir
        self.agndir = agndir
        self.srcdir = srcdir
        self.pulsars = pulsars
        self.agnlist = agnlist
        self.cachedir = cachedir
        self.irf = irf
        self.cache = True
        self.pulse_ons = []         #pulsar on pulse angular distributions
        self.pulse_offs = []        #pulsar off pulse angular distributions
        self.agns = []              #agn angular distributions
        self.angbins=[]             #angular bins
        self.midpts = []            #midpoints of angular bins
        self.ponhists=[]            #pulsar on pulse histograms
        self.pofhists=[]            #pulsar off pulse histograms
        self.agnhists=[]            #agn histograms
        self.nbins = 0              #number of angular bins
        self.halomodel=''
        self.haloparams=[]
        self.mode=-1
        self.__dict__.update(kwargs)


    ######################################################################
    #          Loads data from FT1 files for stacked sources             #
    ######################################################################
    ## loads photons from ft1 and bin the data
    #  @param minroi minimum angular separation (degrees)
    #  @param maxroi maximum angular separation (degrees)
    #  @param emin minimum energy (MeV)
    #  @param emax maximum energy (MeV)
    #  @param tmin minimum time range (MET)
    #  @param tmax maximum time range (MET)
    #  @param ctype conversion type (0:front, 1:back, -1:all)
    def loadphotons(self,minroi,maxroi,emin,emax,tmin,tmax,ctype):
        self.minroi = minroi
        self.maxroi = maxroi
        self.ctype = ctype
        self.emin=emin
        self.emax=emax
        self.ebar=np.sqrt(self.emin*self.emax)

        tag = '%1.2f%1.2f%1.2f%1.2f%1.0f%1.0f%1.0f'%(minroi,maxroi,emin,emax,tmin,tmax,ctype)

        #load pulsar data
        for psr in self.pulsars:

            if os.path.exists(self.cachedir+'%son%s.npy'%(psr[0],tag)):
                print 'Loaded %s on pulse from cache'%(psr[0])
                hist = np.load(self.cachedir+'%son%s.npy'%(psr[0],tag))
                self.pulse_ons.append(hist)
            else:
                sl = StackLoader(lis=psr[0],irf=self.irf,srcdir=self.srcdir,useft2s=False)
                sl.files = [self.pulsdir + psr[0]+ 'on-ft1.fits']
                sl.loadphotons(minroi,maxroi,emin,emax,tmin,tmax,ctype)
                sl.getds()
                self.pulse_ons.append(np.array(cp.copy(sl.ds)))
                if self.cache:
                    np.save(self.cachedir+'%son%s.npy'%(psr[0],tag),np.array(cp.copy(sl.ds)))
                del sl

            if os.path.exists(self.cachedir+'%soff%s.npy'%(psr[0],tag)):
                print 'Loaded %s off pulse from cache'%(psr[0])
                hist = np.load(self.cachedir+'%soff%s.npy'%(psr[0],tag))
                self.pulse_offs.append(hist)
            else:
                sl = StackLoader(lis=psr[0],irf=self.irf,srcdir=self.srcdir,useft2s=False)
                sl.files = [self.pulsdir + psr[0]+ 'off-ft1.fits']
                sl.loadphotons(minroi,maxroi,emin,emax,tmin,tmax,ctype)
                sl.getds()
                self.pulse_offs.append(np.array(cp.copy(sl.ds)))
                if self.cache:
                    np.save(self.cachedir+'%soff%s.npy'%(psr[0],tag),np.array(cp.copy(sl.ds)))
                del sl

        #load agn data
        for lists in self.agnlist:
            if os.path.exists(self.cachedir+'%s%s.npy'%(lists,tag)):
                print 'Loaded %s from cache'%(lists)
                hist = np.load(self.cachedir+'%s%s.npy'%(lists,tag))
                self.agns.append(hist)
            else:
                sl = StackLoader(lis=lists,irf=self.irf,srcdir=self.srcdir,useft2s=False)
                sl.files = glob.glob(self.agndir+'*-ft1.fits')
                sl.loadphotons(minroi,maxroi,emin,emax,tmin,tmax,ctype)
                sl.getds()
                self.agns.append(np.array(cp.copy(sl.ds)))
                if self.cache:
                    np.save(self.cachedir+'%s%s.npy'%(lists,tag),np.array(cp.copy(sl.ds)))
                del sl


    ######################################################################
    #   Bins the FT1 data into angular bins that are adaptive or fixed   #
    ######################################################################
    ## adaptively bins angular distributions in angle or sqrt
    #  @param bins number of angular bins, -1 for sqrt(N) bins
    def bindata(self,bins=8):
        alldata = []
        
        #determine needed bins by combining all data (except background)
        chist=[]
        for puls in self.pulse_ons:
            for sep in puls:
                alldata.append(sep)
                chist.append(1.)
        for it1,puls in enumerate(self.pulse_offs):
            for sep in puls:
                alldata.append(sep)
                chist.append(-self.pulsars[it1][1])
        #for sep in self.agns[0]:
        #    alldata.append(sep)
        alldata = np.array(alldata)
        key = np.argsort(alldata)
        chist = np.array(chist)[key]
        alldata = alldata[key]


        #adaptive binning
        if bins>0 and len(alldata)>20:
            chist = np.array([sum(chist[:x+1]) for x in range(len(chist))])
            chist = chist/max(chist)
            bins = bins
            cumm = np.array([(1.*x+1.)/len(alldata) for x in range(len(alldata))])      #cumulative dist function
            ct = (1.*np.arange(0,bins+1,1))/bins                                          #cumulative fractions, [0,1/bins,2/bins...(bins-1)/bins]
            mask = np.array([max(0,len(chist[chist<x])-1) for x in ct])
            xbins = alldata[mask]#np.array([alldata[max(0,len(chist[chist<x])-1)] for x in ct])         #bin edges corresponding to fractions
            self.angbins = xbins

        # sqrt(N) binning
        else:
            if len(alldata)>20:
                bins = int(np.sqrt(len(alldata)))
            else:
                bins = int(np.sqrt(len(self.agns[0])))
            xbins = np.arange(0,bins,1)/(1.*bins)
            minimum = min(min(alldata),min(self.agns[0]))*rd
            xbins =  minimum + xbins*(self.maxroi-minimum)
            self.angbins = xbins/rd

        #did you already do it?
        if self.ponhists==[]:
            for it1,puls in enumerate(self.pulse_ons):
                self.ponhists.append(np.histogram(puls,self.angbins)[0])
                self.pofhists.append(np.histogram(self.pulse_offs[it1],self.angbins)[0])
            for it1,agns in enumerate(self.agns):
                self.agnhists.append(np.histogram(agns,self.angbins)[0])

        self.angbins = self.angbins*rd           #convert to degrees
        self.nbins = len(self.angbins)-1         #lop of bin edge for bin center
        self.iso = np.array([(self.angbins[it+1]**2-self.angbins[it]**2)/(max(self.angbins)**2-min(self.angbins)**2) for it in range(self.nbins)])  #isotropic model
        self.midpts = np.array([(self.angbins[it+1]+self.angbins[it])/2. for it in range(self.nbins)])           #bin midpoint
        self.widths = np.array([(self.angbins[it+1]-self.angbins[it])/2. for it in range(self.nbins)])           #bin widths
        self.areas = np.array([self.angbins[it+1]**2-self.angbins[it]**2 for it in range(self.nbins)])           #jacobian

    ######################################################################
    #    Sets up Minuit and determines maximum likelihood parameters     #
    ######################################################################
    ## maximizes likelihood
    # possible keyword arguments
    # @param halomodel string corresponding to any angular model in angularmodels.py
    # @param haloparams array of model parameters for halomodel
    def fit(self,**kwargs):
        self.__dict__.update(kwargs)

        print ''
        print '**********************************************************'
        print '*                                                        *'
        print '*             Combined Likelihood Analysis               *'
        print '*                                                        *'
        print '**********************************************************'
        psrs = ''
        for psl in self.pulsars:
            psrs = psrs + '%s\t'%psl[0]
        print 'Pulsars: %s'%psrs
        agns = ''
        for agnl in self.agnlist:
            agns = agns + '%s\t'%agnl
        print 'AGNs: %s'%agns
        print 'Using halo model: %s'%self.halomodel
        pars = ''
        for par in self.haloparams:
            pars = pars + '%1.6f\t'%par
        print 'Using parameters: %s'%pars
        print '**********************************************************'

        psf = CALDBPsf(CALDBManager(irf=self.irf))
        fint = psf.integral(self.ebar,self.ctype,max(self.angbins)/rd,min(self.angbins)/rd)
        self.psfm = np.array([psf.integral(self.ebar,self.ctype,self.angbins[it+1]/rd,self.angbins[it]/rd)/fint for it in range(self.nbins)])

        #set up initial psf parameters (uniform)
        params = [self.psfm[x] for x in range(self.nbins)]
        limits = [[-1,1] for x in range(self.nbins)]
        fixed = [False for x in range(self.nbins)]

        psrs = len(self.ponhists)
        agns = len(self.agnhists)

        #pulsar estimators
        for hist in self.ponhists:
            params.append(sum(hist)/2.)
            limits.append([-sum(hist)*100,sum(hist)*100])
            fixed.append(False)

        #agn estimators
        for hist in self.agnhists:
            params.append(sum(hist)/2.)
            limits.append([-sum(hist)*100,sum(hist)*100])
            fixed.append(False)

        #iso estimator
        params.append(1.)
        limits.append([-sum(self.agnhists[0])*100,sum(self.agnhists[0])*100])
        fixed.append(False)

        self.Nh=[0]
        self.Nhe=1e-40
        if self.halomodel=='':
            self.hmd = np.zeros(self.nbins)
        else:
            halomodel = eval(self.halomodel)
            if self.haloparams[0]<0:
                return np.Infinity
            mod = halomodel(lims=[min(self.angbins),max(self.angbins)],model_par=self.haloparams)
            mint = mod.integral(min(self.angbins)/rd,max(self.angbins)/rd)
            self.hmd = np.array([mod.integral(self.angbins[it]/rd,self.angbins[it+1]/rd)/mint for it in range(self.nbins)])

        params.append(self.Nh[0])
        limits.append([0,sum(self.agnhists[0])])
        fixed.append(self.halomodel=='')
        print 'Setting up Minuit and maximizing'
        ############  setup Minuit and optimize  ###############
        self.minuit = Minuit(self.likelihood,params,gradient=self.gradient,force_gradient=1,fixed=fixed,limits=limits,strategy=2,tolerance=1e-10,printMode=self.mode)
        self.minuit.minimize()
        print 'Likelihood value: %1.1f'%self.minuit.fval[0]
        print '**********************************************************'
        #self.gradient(self.minuit.params,True)
        ###########  get parameters and errors #################
        self.errs = self.minuit.errors()#method='MINOS')
        """self.errs = []
        #for it in range(len(self.minuit.params)):
        #    eplus,eminus,ecurv,gcc = Double(),Double(),Double(),Double()
        #    self.minuit.minuit.mnerrs(it,eplus,eminus,ecurv,gcc)
        #    self.errs.append(float(ecurv))
        #self.errs = np.array(self.errs)"""
        self.errs2 = [self.errors(it) for it in range(len(self.minuit.params))]#self.errs[it][it] for it in range(len(self.minuit.params))]
        #self.errs2 = self.errs
        self.errs2 = [self.finderrs(it) for it in range(len(self.minuit.params))]
        self.psf = self.minuit.params[:self.nbins]
        scale = sum(self.psf)                                                                                          #normalize psf
        self.psf = self.psf/scale                                                                                      #PSF
        self.psfe = np.array([np.sqrt(self.errs2[i])/scale for i in range(self.nbins)])                              #PSF errors
        self.Npj = self.minuit.params[self.nbins:self.nbins+psrs]*scale                                                #PSR number est
        self.Npje = np.array([np.sqrt(self.errs2[self.nbins+i])*scale for i in range(psrs)])              #PSR number est errors
        self.Naj = self.minuit.params[self.nbins+psrs:self.nbins+psrs+agns]*scale                                      #AGN number est
        self.Naje = np.array([np.sqrt(self.errs2[self.nbins+psrs+i])*scale for i in range(agns)])    #AGN number errors
        self.Ni  = self.minuit.params[self.nbins+psrs+agns:self.nbins+psrs+agns+agns]                                  #isotropic number est
        self.Nie = [np.sqrt(self.errs2[self.nbins+psrs+agns+i]) for i in range(agns)]           #isotropic number est errors
        if self.halomodel!='':
            self.Nh = self.minuit.params[self.nbins+psrs+agns+agns:self.nbins+psrs+agns+agns+1]                                 #halo est
            self.Nhe = np.sqrt(self.errs2[self.nbins+psrs+agns+agns])                                    #halo err
        print ''
        print '--------- Pulsars-------------'
        for it,nj in enumerate(self.Npj):
            print 'N(%s) = %1.0f (1 +/- %1.2f)'%(self.pulsars[it][0],nj,self.Npje[it]/nj)
        print ''
        print '--------- AGN    -------------'
        for it,nj in enumerate(self.Naj):
            print 'Npsf(%s) = %1.0f (1 +/- %1.2f)'%(self.agnlist[it],nj,self.Naje[it]/nj)
            print 'Niso(%s) = %1.0f (1 +/- %1.2f)'%(self.agnlist[it],self.Ni[it],self.Nie[it]/self.Ni[it])
        print ''
        if self.halomodel!='':
            print 'Nhalo = %1.0f (1 +/- %1.2f)'%(self.Nh[0],self.Nhe/self.Nh[0])

        #for it in range(len(self.minuit.params)):
        #    print np.sqrt(self.errs[it][it]),np.sqrt(self.errs2[it])

        """seps = np.arange(-2.0,2.1,0.1)
        py.figure(figsize=(16,16))
        rows = int(np.sqrt(len(self.minuit.params)))+1

        for it in range(len(self.minuit.params)):
            py.subplot(rows,rows,it+1)
            er = np.zeros(len(self.minuit.params))
            er[it] = np.sqrt(self.errs2[it])
            like = []
            for x in seps:
                modif = self.minuit.params+er*x
                tlike = self.minuit.fval-self.likelihood(modif)
                like.append(tlike)
            py.plot(seps,like)
        py.savefig('likes.png')"""

        ########  calculate background estimators  ###########
        self.vij = []
        self.vije = []

        #loop over pulsars
        for it1,row in enumerate(self.ponhists):

            tvij = []
            tvije = []
            N = self.Npj[it1]               #pulsar number estimator
            a = self.pulsars[it1][1]        #ratio of on-off

            #loop over angular bins
            for it2,n in enumerate(row):
                #n on pulse in current bin
                m = self.psf[it2]                                        #PSF in current bin
                b = self.pofhists[it1][it2]                              #off pulse in current bin
                v = self.backest(a,n,b,m,N)                              #background number estimator
                tvij.append(v)

                #estimate errors by propagation
                dvdm = sm.derivative(lambda x: self.backest(a,n,b,x,N),m,m/10.)   #background/psf derivative
                dvdN = sm.derivative(lambda x: self.backest(a,n,b,m,x),N,N/10.)   #background/psr number estimator derivative
                cov = self.errs[it2][self.nbins+it1]                              #covariance of psf and number estimator
                Ne = self.Npje[it1]
                me = self.psfe[it2]
                ve = np.sqrt((dvdm*me)**2+(dvdN*Ne)**2)      #naive error propagation
                tvije.append(ve)

            self.vij.append(tvij)
            self.vije.append(tvije)

        self.vij = np.array(self.vij)                                        #PSR background number estimator
        self.vije = np.array(self.vije)                                      #PSR background number estimator errors

        return self.minuit.fval[0]


    ######################################################################
    #      Likelihood function from (3) in paper                         #
    ######################################################################
    ## likelihood function
    #  @param params likelihood function parameters
    def likelihood(self,params):#npij,bpij,naij,mi,Npj,Naj,Ni,Nh=0):

        psrs = len(self.ponhists)
        agns = len(self.agnhists)

        npij = self.ponhists
        bpij = self.pofhists
        naij = self.agnhists
        mi = params[:self.nbins]
        Npj = params[self.nbins:self.nbins+psrs]
        Naj = params[self.nbins+psrs:self.nbins+psrs+agns]
        Ni = params[self.nbins+psrs+agns:self.nbins+psrs+agns+agns]
        Nh = params[self.nbins+psrs+agns+agns:self.nbins+psrs+agns+agns+1]
        acc = 0
        verb=False    #set to true for slow,verbose output

        ########################################
        #          first sum in (3)            #
        ########################################
        #loop over pulsars
        for it1,row in enumerate(npij):

            N = Npj[it1]                    #pulsar number estimator
            a = self.pulsars[it1][1]        #ratio of on-off

            #loop over angular bins
            for it2,n in enumerate(row):
                #n on pulse in current bin
                m = mi[it2]                                     #PSF in current bin
                b = bpij[it1][it2]                              #off pulse in current bin

                v = self.backest(a,n,b,m,N)                     #get background estimator

                #catch negative log terms
                lterm = N*m+a*v
                if lterm <0. or v<0.:
                    print lterm,v
                    return np.Infinity

                if n>0:
                    acc = acc - n*np.log(lterm)
                acc = acc + N*m + a*v

                if b>0:
                    acc = acc - b*np.log(v)
                acc = acc + v

                if verb:
                    print n,b,N,m,a,v,lterm,acc
                    t.sleep(0.25)
        

        ########################################
        #         second sum in (3)            #
        ########################################
        #loop over agn
        for it1,row in enumerate(naij):

            #loop over angular bins
            for it2,bin in enumerate(row):

                #make sure log term is proper
                lterm = Naj[it1]*mi[it2]+Ni[0]*self.iso[it2] + Nh*self.hmd[it2]
                if lterm<0.:
                    return np.Infinity

                if bin>0:
                    acc = acc - bin*np.log(lterm)
                acc = acc + Naj[it1]*mi[it2] + Ni[it1]*self.iso[it2] + Nh*self.hmd[it2]

                if verb:
                    print bin,Naj[it1],mi[it2],Ni[it1],lterm,self.iso[it2],acc,Nh,self.hmd[it2]
                    t.sleep(0.25)
        return acc


    ######################################################################
    #      Makes plots of PSR, AGN fits, PSF and background residuals    #
    ######################################################################
    ## outputs a plot of the distributions
    # @param name output PNG filename
    def makeplot(self,name):
        py.ioff()
        py.figure(1,figsize=(16,16))
        py.clf()

        #########  Pulsars  ############
        ax = py.subplot(2,2,1)
        ax.set_yscale("log", nonposy='clip')
        ax.set_xscale("log", nonposx='clip')
        py.title('Pulsars')
        names = []
        pts = []
        mi = 1e40
        ma = 0
        amask = self.areas>0
        for it,hist in enumerate(self.ponhists):
            p1 = py.errorbar(self.midpts,(hist)/self.areas,xerr=self.widths,yerr=np.sqrt(hist)/self.areas,marker='o',ls='None')
            p2 = py.errorbar(self.midpts,(self.pofhists[it])/self.areas,xerr=self.widths,yerr=np.sqrt(self.pofhists[it])/self.areas,marker='o',ls='None')
            p3 = py.errorbar(self.midpts,(self.Npj[it]*self.psf+self.pulsars[it][1]*self.vij[it])/self.areas,xerr=self.widths,yerr=np.sqrt((self.Npje[it]*self.psf)**2+(self.Npj[it]*self.psfe)**2)/self.areas,marker='o',ls='None')
            names.append(self.pulsars[it][0]+' ON')
            pts.append(p1[0])
            names.append(self.pulsars[it][0]+' OFF')
            pts.append(p2[0])
            names.append(self.pulsars[it][0]+' model')
            pts.append(p3[0])
            mi = min(mi,max((self.pofhists[it][amask])/self.areas[amask]))
            ma = max(ma,max((self.Npj[it]*self.psf[amask]+self.pulsars[it][1]*self.vij[it][amask])/self.areas[amask]))
        py.xlabel(r'$\theta\/(\rm{deg})$')
        py.ylabel(r'$dN/d\theta^{2}$')
        py.grid()
        mi = max(mi,1./max(self.areas[amask]))
        py.xlim(min(self.angbins),max(self.angbins))
        py.ylim(0.25*mi,2*ma)
        py.legend(pts,names)

        #########  AGN plots  #############
        ax = py.subplot(2,2,2)
        ax.set_yscale("log", nonposy='clip')
        ax.set_xscale("log", nonposx='clip')
        py.title('AGN')
        names = []
        pts = []
        for it,hist in enumerate(self.agnhists):
            model = self.Naj[it]*self.psf+self.Ni[it]*self.iso + self.Nh[0]*self.hmd
            #print self.Naj[it],self.psf,self.Ni[it],self.iso,self.Nh[0],self.hmd
            modelerrs = np.sqrt((self.Naj[it]*self.psf/sum(self.psf)*np.sqrt((self.psfe/self.psf)**2+(self.Naje[it]/self.Naj[it])**2))**2+(self.Nie[it]*self.iso)**2+(self.Nhe*self.hmd)**2)
            back = self.Ni[it]*self.iso
            backerrs = self.Nie[it]*self.iso
            p1 = py.errorbar(self.midpts,hist/self.areas,xerr=self.widths,yerr=np.sqrt(hist)/self.areas,marker='o',ls='None')
            p2 = py.errorbar(self.midpts,(model)/self.areas,xerr=self.widths,yerr=np.sqrt(model)/self.areas,marker='o',ls='None')
            p3 = py.errorbar(self.midpts,back/self.areas,xerr=self.widths,yerr=backerrs/self.areas,marker='o',ls='None')
            names.append(self.agnlist[it]+' Data')
            pts.append(p1[0])
            names.append(self.agnlist[it]+' Model')
            pts.append(p2[0])
            names.append(self.agnlist[it]+' Iso')
            pts.append(p3[0])
            if self.halomodel!='':
                p4 = py.errorbar(self.midpts,self.Nh[0]*self.hmd,xerr=self.widths,yerr=(self.Nhe*self.hmd)/self.areas,marker='o',ls='None')
                names.append('Halo')
                pts.append(p4[0])
        py.xlabel(r'$\theta\/(\rm{deg})$')
        py.ylabel(r'$dN/d\theta^{2}$')
        py.xlim(min(self.angbins),max(self.angbins))
        py.ylim(0.25*mi,2*max(hist[amask]/self.areas[amask]))
        py.grid()
        py.legend(pts,names)

        ############  PSF residuals plot  ###############
        ax = py.subplot(2,2,3)
        names = []
        pts = []
        ax.set_xscale("log", nonposx='clip')
        err = np.ones(self.nbins)
        py.errorbar(self.midpts,(self.psf-self.psfm)/self.psfm,xerr=self.widths,yerr=self.psfe/self.psfm,ls='None',marker='o')
        cmask = self.psfe>0
        chisq = sum(((self.psf[cmask]-self.psfm[cmask])/self.psfe[cmask])**2)

        py.grid()
        ma = max(abs((self.psf-self.psfm+self.psfe)/self.psfm))
        ma = max(ma,max(abs((self.psf-self.psfm-self.psfe)/self.psfm)))
        py.xlim(min(self.angbins),max(self.angbins))
        py.ylim(-1.5*ma,1.5*ma)
        py.title('PSF residuals from %s'%self.irf)
        py.xlabel(r'$\theta\/(\rm{deg})$')
        py.ylabel(r'$(\rm{Data - Model})/Model$')
        py.figtext(0.3,0.4,'Chisq (dof) = %1.1f (%1.0f)'%(chisq,self.nbins))
        
        ##############  PSR Background estimators  ######
        ax = py.subplot(2,2,4)
        ax.set_xscale("log", nonposx='clip')
        names = []
        pts = []
        ma = 0.
        for it,psr in enumerate(self.pofhists):
            try:
                py.errorbar(self.midpts,(psr-self.vij[it])/self.vij[it],xerr=self.widths,yerr=self.vije[it]/self.vij[it],ls='None',marker='o')
                mask = psr>0
                up = max((psr[mask]-self.vij[it][mask]+self.vije[it][mask])/self.vij[it][mask])
                down = min((psr[mask]-self.vij[it][mask]-self.vije[it][mask])/self.vij[it][mask])
                ma = max(ma,up)
                ma = max(ma,abs(down))
            except:
                print 'Bad plotting' 
        py.grid()
        py.title('PSR Background Estimator Residuals')
        py.xlabel(r'$\theta\/(\rm{deg})$')
        py.ylabel(r'$(\rm{Data - Model})/Model$')
        py.xlim(min(self.angbins),max(self.angbins))
        py.ylim(-1.5*ma,1.5*ma)
        py.savefig(name+'.png')

############################################   Helper functions  ##############################################################


    ######################################################################
    #    Determination of maximum likelihood estimator of vij from (3)   #
    ######################################################################
    ## the maximum likelhood estimator of the pulsar background
    # @param a ratio of on/off phase window             (observation)
    # @param n number of photons in on window bin       (observation)
    # @param b bumber of photons in off window bin      (observation)
    # @param m PSF in bin                               (derived)
    # @param N number of photons associated with pulsar (derived)
    def backest(self,a,n,b,m,N):

        sterm = 4*a*(1+a)*b*m*N+(m*N-a*(b+n-m*N))**2    #discriminant
        #catch negative discriminant
        if sterm<0.:
            print 'Unphysical Solution: %1.4f'%sterm

        #calculate background estimator analytically
        v = a*(b+n)-m*N-a*m*N+np.sqrt(sterm)
        v = v/(2.*a*(1+a))
        return v

    ######################################################################
    #    Gradient of maximum likelihood estimator of vij from (3)        #
    ######################################################################
    ## the maximum likelhood estimator of the pulsar background
    # @param a ratio of on/off phase window             (observation)
    # @param n number of photons in on window bin       (observation)
    # @param b bumber of photons in off window bin      (observation)
    # @param m PSF in bin                               (derived)
    # @param N number of photons associated with pulsar (derived)
    def gradback(self,a,n,b,m,N):
        sterm = 4*a*(1+a)*b*m*N+(m*N-a*(b+n-m*N))**2    #discriminant
        #catch negative discriminant
        if sterm<0.:
            print 'Unphysical Solution: %1.4f'%sterm

        #calculate gradient of background estimator analytically
        grad1 = -N-a*N+(4*a*(1+a)*b*N+2*(m*N-a*(b+n-m*N))*(N-a*(-N)))/(2*np.sqrt(sterm))    #psf derivative
        grad2 = -m-a*m+(4*a*(1+a)*b*m+2*(m*N-a*(b+n-m*N))*(m-a*(-m)))/(2*np.sqrt(sterm))    #number estimator derivative
        v = np.array([grad1,grad2])
        v = v/(2.*a*(1+a))
        return v

    ######################################################################
    #         Gradient of maximum likelihood from (3)                    #
    ######################################################################
    ## The gradient of the maximum likelhood estimator
    # @param params likelihood parameters defined by likelihood function
    # @param verb verbose slow output of gradient calculation
    def gradient(self,params,verb=False):

        psrs = len(self.ponhists)
        agns = len(self.agnhists)

        npij = self.ponhists
        bpij = self.pofhists
        naij = self.agnhists
        mi = params[:self.nbins]
        Npj = params[self.nbins:self.nbins+psrs]
        Naj = params[self.nbins+psrs:self.nbins+psrs+agns]
        Ni = params[self.nbins+psrs+agns:self.nbins+psrs+agns+agns]
        Nh = params[self.nbins+psrs+agns+agns:self.nbins+psrs+agns+agns+1]
        grad = []
        if verb:
            print 'Obs\tmod\tfact\tnum\tacc'
            print '----------------------'

        #PSF gradient
        for it in range(self.nbins):
            acc = 0
            flag = False
            for it2 in range(psrs):
                alpha = self.pulsars[it2][1]
                denom = Npj[it2]*mi[it]+alpha*self.backest(alpha,npij[it2][it],bpij[it2][it],mi[it],Npj[it2])
                grad0 = self.gradback(alpha,npij[it2][it],bpij[it2][it],mi[it],Npj[it2])[0]
                if denom <=0:
                    flag=True
                acc = acc + (Npj[it2]+alpha*grad0)*(npij[it2][it]/(denom) - 1.)
                if verb:
                    print npij[it2][it],denom,(npij[it2][it]/(denom) - 1.),Npj[it2],alpha*grad0,acc
                    t.sleep(0.25)

            for it2 in range(agns):
                denom = Naj[it2]*mi[it]+Ni[it2]*self.iso[it]+Nh[0]*self.hmd[it]
                if denom <=0:
                    flag=True
                acc = acc + Naj[it2]*(naij[it2][it]/(denom) - 1.)
                if verb:
                    print naij[it2][it],denom,(naij[it2][it]/(denom) - 1.),Naj[it2],acc
                    t.sleep(0.25)

            if flag:
                grad.append(-np.Infinity)
            else:
                grad.append(-acc.item())
            if verb:
                print '----------------------'

        #Pulsar Number estimator gradient
        for it2 in range(psrs):
            alpha = self.pulsars[it2][1]
            flag = False
            acc = 0
            for it in range(self.nbins):
                denom = Npj[it2]*mi[it]+alpha*self.backest(alpha,npij[it2][it],bpij[it2][it],mi[it],Npj[it2])
                grad1 = self.gradback(alpha,npij[it2][it],bpij[it2][it],mi[it],Npj[it2])[1]
                if denom <=0:
                    flag=True
                acc = acc + (mi[it]+alpha*grad1)*(npij[it2][it]/denom - 1.)
                if verb:
                    print npij[it2][it],denom,mi[it],alpha*grad1,acc
                    t.sleep(0.25)
            if flag:
                grad.append(-np.Infinity)
            else:
                grad.append(-acc.item())
            if verb:
                print '----------------------'

        #AGN number estimator gradient
        for it2 in range(agns):
            acc = 0
            flag = False
            for it in range(self.nbins):
                denom = Naj[it2]*mi[it]+Ni[it2]*self.iso[it]+Nh[0]*self.hmd[it]
                if denom <=0:
                    flag=True
                acc = acc + mi[it]*(naij[it2][it]/denom - 1.)
                if verb:
                    print naij[it2][it],denom,acc
                    t.sleep(0.25)
            if flag:
                grad.append(-np.Infinity)
            else:
                grad.append(-acc.item())
            if verb:
                print '----------------------'

        #Isotropic number estimator gradient for AGN
        for it2 in range(agns):
            acc = 0
            flag = False
            for it in range(self.nbins):
                denom = Naj[it2]*mi[it]+Ni[it2]*self.iso[it]+Nh[0]*self.hmd[it]
                if denom <=0:
                    flag=True
                acc = acc + self.iso[it]*(naij[it2][it]/denom - 1.)
                if verb:
                    print naij[it2][it],denom,acc
                    t.sleep(0.25)
            if flag:
                grad.append(-np.Infinity)
            else:
                grad.append(-acc.item())
            if verb:
                print '----------------------'
        

        #Halo number estimator gradient for AGN
        acc = 0
        flag = False
        for it2 in range(agns):
            for it in range(self.nbins):
                denom = Naj[it2]*mi[it]+Ni[it2]*self.iso[it]+Nh[0]*self.hmd[it]
                if denom <=0:
                    flag=True
                acc = acc + self.hmd[it]*(naij[it2][it]/denom - 1.)
                if verb:
                    print naij[it2][it],denom,acc
                    t.sleep(0.25)
        if flag:
            grad.append(-np.Infinity)
        else:
            grad.append(-acc.item())
        if verb:
            print '----------------------'
        
        return np.array(grad)

    ######################################################################
    #        Simple Error calculation from likelihood (1D)               #
    ######################################################################
    ## Error calculation about the maximum for one parameter (no covariance)
    # @param num number of parameter to find error
    def errors(self,num):
        eig = np.zeros(len(self.minuit.params))
        eig[num]=1.
        if self.mode>0:
            disp = 1
        else:
            disp = 0
        
        #find points on either side of maximum where likelihood has decreased by 1/2
        err1 = so.fmin_powell(lambda x: abs(self.likelihood(self.minuit.params+x[0]*eig)-self.minuit.fval-0.5),[self.minuit.params[num]*0.01],full_output=1,disp=disp)
        err1 = abs(err1[0])
        err2 = so.fmin_powell(lambda x: abs(self.likelihood(self.minuit.params-x[0]*eig)-self.minuit.fval-0.5),[self.minuit.params[num]*0.01],full_output=1,disp=disp)
        err2 = abs(err2[0])

        #try to catch badly formed likelihood surfaces
        if self.likelihood(self.minuit.params-err1*eig)==np.Infinity:
            return err2*err2
        if self.likelihood(self.minuit.params+err2*eig)==np.Infinity:
            return err1*err1
        return err1*err2

    ######################################################################
    #      Covariant error estimation from the likelihood surface        #
    ######################################################################
    ## Estimates the true error by projecting the surface in multiple dimensions
    # @param num number of parameter to find error
    def finderrs(self,num):
        ma = 0.
        err = np.sqrt(self.errs2[num])
        rt = np.sqrt(2)

        #py.figure(2,figsize=(16,16))
        #py.clf()
        rows = int(np.sqrt(len(self.minuit.params)))+1
        #go through all parameters
        #find the quadratic form of the likelihood surface
        #determine the increase in the variance from covariance of parameters
        for it in range(len(self.minuit.params)):

            if it!=num:
                #py.subplot(rows,rows,it+1)
                eigx = np.zeros(len(self.minuit.params))
                eigx[num]=err
                eigy = np.zeros(len(self.minuit.params))
                eigy[it]=np.sqrt(self.errs2[it])

                #calulate likelihood along ring around maximum (1-sigma in likelihood)
                px = (self.likelihood(self.minuit.params+eigx)-self.minuit.fval)[0]
                pxpy = (self.likelihood(self.minuit.params+(eigx+eigy)/rt)-self.minuit.fval)[0]
                py1 = (self.likelihood(self.minuit.params+eigy)-self.minuit.fval)[0]
                mxpy = (self.likelihood(self.minuit.params+(-eigx+eigy)/rt)-self.minuit.fval)[0]
                mx = (self.likelihood(self.minuit.params-eigx)-self.minuit.fval)[0]
                mxmy = (self.likelihood(self.minuit.params+(-eigx-eigy)/rt)-self.minuit.fval)[0]
                my = (self.likelihood(self.minuit.params-eigy)-self.minuit.fval)[0]
                pxmy = (self.likelihood(self.minuit.params+(eigx-eigy)/rt)-self.minuit.fval)[0]
                q = [px,pxpy,py1,mxpy,mx,mxmy,my,pxmy]
                
                """gridpts = 12
                minmax = 5.
                vals = np.arange(-gridpts,gridpts+1,1)
                vals = vals*minmax/gridpts
                z = np.array([self.likelihood(self.minuit.params+eigx*x+eigy*y)-self.minuit.fval for x in vals for y in vals]).reshape(len(vals),-1)
                py.contour(vals,vals,z,[0.5,2.,4.5,8.,12.5])
                #py.colorbar()
                py.xlim(-minmax,minmax)
                py.ylim(-minmax,minmax)"""
                #find quadratic fit to likelihood surface
                try:
                    el = Ellipse(q)
                    """x,y=el.contour(1/np.sqrt(2))
                    py.plot(x,y,'-')
                    ma = max(max(x),max(y))*1.5
                    py.xlim(min(-2,-ma),max(2,ma))
                    py.ylim(min(-2,-ma),max(2,ma))"""


                    pars = el.qf.p
                    a,b,c = (pars[0]-pars[4]*pars[4]/(4.*pars[2])),pars[1],(-0.5-pars[3]*pars[3]/(4.*pars[2]))

                    #parameter we're interested in is x-axis
                    #find the x-value tangent at quadratic surface = 0.5
                    xmin = abs(-b/(2*a)+np.sqrt(b**2-4*a*c)/(2*a))
                    ymin = -(pars[3]+pars[4]*xmin)/(2*pars[2])
                    terr = abs(xmin)

                    #is it the largest?
                    ma = max(ma,terr)

                    #print xmin,ymin
                    #t.sleep(0.25)
                except:
                    pass
                    #print 'Caught poorly formed quad surface'
        #py.savefig('likes%d.png'%num)

        return (ma*err)**2

############################################   End of CombinedLike Class ######################################################


############ unit test ##########################
## test function
# @param bins number of adaptive bins
# @param ctype conversion type 0:front, 1:back
# @param emin minimum energy
# @param emax maximum energy
# @param days number of days of data to examine from start of P6 data
def test(bins=8,ctype=0,emin=1000,emax=1778,days=30,irf='P6_v3_diff',maxr=-1):
    psf = CALDBPsf(CALDBManager(irf=irf))
    ebar = np.sqrt(emin*emax)
    if maxr<0:
        maxr = psf.inverse_integral(ebar,ctype,99.5)*1.5             #use 1.5 times the 99.5% containment as the maximum distance
    cl = CombinedLike(irf=irf,mode=-1)
    cl.loadphotons(0,maxr,emin,emax,239517417,239517417+days*86400,ctype)
    cl.bindata(bins)
    f0 = cl.fit()
    cl.makeplot('figures/%s_emi%1.0f_ema%1.0f_ec%1.0f_roi%1.2f_bins%1.0f'%(cl.agnlist[0],emin,emax,ctype,maxr,bins))
    f1=[]
    #bestp = so.fmin_powell(lambda x:cl.fit(halomodel='Halo',haloparams=[x[0]/rd]),(0.4),full_output=1)
    #print 'Halo size was: %1.2f'%bestp[0]
    #print 'TS was: %1.1f'%(2*(f0-bestp[1]))
    #for it in (np.arange(1.,10.,1.)/10.):
    #it=bestp[0]
    #f1.append(cl.fit(halomodel='Halo',haloparams=[it/rd]))
    #cl.makeplot('figures/%s_emi%1.0f_ema%1.0f_ec%1.0f_roi%1.2f_bins%1.0f_%1.1fhalo'%(cl.agnlist[0],emin,emax,ctype,maxr,bins,it))