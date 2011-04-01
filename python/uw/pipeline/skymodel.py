"""
Manage the sky model for the UW all-sky pipeline
$Header: /nfs/slac/g/glast/ground/cvs/pointlike/python/uw/pipeline/skymodel.py,v 1.19 2011/03/28 17:21:00 burnett Exp $

"""
import os, pickle, glob, types
import numpy as np
from skymaps import SkyDir, Band
from uw.utilities import keyword_options, makerec
#  this is below: only needed when want to create XML
#from uw.utilities import  xml_parsers
from ..like import Models

from . import sources, catrec

class SkyModel(object):
    """
    Define a model of the gamma-ray sky, including point, extended, and global sources.
    Input is currently only from a folder containing all of the ROI pickles, in the format generated by the pipeline.
    Thus pipeline is completely iterative.
    
    Implement methods to create ROI for pointlike, used by pipeline.
    """
    
    defaults= (
        ('extended_catalog_name', None,  'name of folder with extended info\n'
                                         'if None, look it up in the config.txt file'),
        ('alias', dict(), 'dictionary of aliases to use for lookup'),
        ('diffuse', None,   'set of diffuse file names; if None, expect config to have'),
        ('use_limb',True,'whether to include the model for the limb emission'),
        ('auxcat', None, 'name of auxilliary catalog of point sources to append or names to remove',),
        ('newmodel', None, 'if not None, a string to eval\ndefault new model to apply to appended sources'),
        ('update_positions', None, 'set to minimum ts  update positions if localization information found in the database'),
        ('free_index', None, 'Set to minimum TS to free photon index if fixed'),
        ('filter',   lambda s: True,   'selection filter'), 
        ('rename_source',  lambda name: name, 'rename function'),
        ('closeness_tolerance', 0., 'if>0, check each point source for being too close to another, print warning'),
        ('quiet',  False,  'make quiet' ),
    )
    
    @keyword_options.decorate(defaults)
    def __init__(self, folder=None,  **kwargs):
        """
        folder : string or None
            name of folder to find all files defining the sky model, including:
             a subfolder 'pickle' with files *.pickle describing each ROI, partitioned as a HEALpix set.
             a file 'config.txt' written by the pipeline
        """
        keyword_options.process(self, kwargs)
        if self.free_index is not None: 
            print 'will free photon indices for ts>%d' % self.free_index

        if folder is None:
            folder = 'uw%02d' % int(open('version.txt').read())
        self.folder = os.path.expandvars(folder)
        if not os.path.exists(self.folder):
            raise Exception('sky model folder %s not found' % folder)
        self.get_config()
        self._setup_extended()
        if self.diffuse is not None:
            """ make a dictionary of (file, object) tuples with key the first part of the diffuse name"""
            assert len(self.diffuse)<4, 'expect 2 or 3 diffuse names'
        else:
            self.diffuse = eval(self.config['diffuse'])
        self.diffuse_dict = sources.DiffuseDict(self.diffuse)
        self._load_sources()
        self.load_auxcat()
        if self.use_limb:
            self.add_limb() #### temporary?
      
    def __str__(self):
        return 'SkyModel %s' %self.folder\
                +'\n\t\tdiffuse: %s' %list(self.diffuse)\
                +'\n\t\textended: %s' %self.extended_catalog_name 
     
    def get_config(self, fn = 'config.txt'):
        """ parse the items in the configuration file into a dictionary
        """
        file = open(os.path.join(self.folder, fn))
        self.config={}
        for line in file:
            item = line.split(':')
            if len(item)>1:
                self.config[item[0].strip()]=item[1].strip()
 
    def load_auxcat(self):
        """ modify the list of pointsources from entries in the auxcat: for now:
            * add it not there
            * move there, at new ra,dec
            * remove if ra<0
        
        """
        if self.auxcat is None or self.auxcat=='': 
            return
        cat = self.auxcat 
        if not os.path.exists(cat):
            cat = os.path.expandvars(os.path.join('$FERMI','catalog', cat))
        if not os.path.exists(cat):
            raise Exception('auxilliary catalog %s not found locally or in $FERMI/catalog'%self.auxcat)
        ss = makerec.load(cat)
        names = [s.name for s in self.point_sources]
        toremove=[]
        print 'process auxcat %s' %cat
        for s in ss:
            sname = s.name.replace('_',' ')
            if sname  not in names: 
                skydir=SkyDir(float(s.ra), float(s.dec))
                index=self.hpindex(skydir)
                self.point_sources.append(sources.PointSource(name=s.name, skydir=skydir, index=index, model=self.newmodel))
                print '\tadded new source %s at ROI %d' % (s.name, index)
            else: 
                print '\t source %s is in the model:' %sname, # will remove if ra<0' % sname
                ps = self.point_sources[names.index(sname)]
                if float(s.ra)<=0: 
                    toremove.append(ps)
                    print ' removed.'
                else:
                    newskydir=SkyDir(float(s.ra),float(s.dec))
                    print 'moved from %s to %s' % (ps.skydir, newskydir)
                    ps.skydir=newskydir
        for ps in toremove:
            self.point_sources.remove(ps)
            
    def _setup_extended(self):
        if self.extended_catalog_name is None:
            self.extended_catalog_name=self.config['extended']
        if not self.extended_catalog_name: return 
        extended_catalog_name = \
            os.path.expandvars(os.path.join('$FERMI','catalog',self.extended_catalog_name))
        if not os.path.exists(extended_catalog_name):
            raise Exception('extended source folder "%s" not found' % extended_catalog_name)
        self.extended_catalog= sources.ExtendedCatalog(extended_catalog_name, alias=self.alias)
        #print 'Loaded extended catalog %s' % self.extended_catalog_name
        
    def _load_sources(self):
        """
        run through the pickled roi dictionaries, create lists of point and extended sources
        assume that the number of such corresponds to a HEALpix partition of the sky
        """
        self.point_sources= []
        files = glob.glob(os.path.join(self.folder, 'pickle', '*.pickle'))
        files.sort()
        self.nside = int(np.sqrt(len(files)/12))
        if len(files) != 12*self.nside**2:
            msg = 'Number of pickled ROI files, %d, found in folder %s, not consistent with HEALpix' \
                % (len(files),os.path.join(self.folder, 'pickle'))
            raise Exception(msg)
        self.global_sources = []  # allocate list to index parameters for global sources
        self.extended_sources=[]  # list of unique extended sources
        self.changed=set() # to keep track of extended models that are different from catalog
        moved=0
        for i,file in enumerate(files):
            p = pickle.load(open(file))
            index = int(os.path.splitext(file)[0][-4:])
            assert i==index, 'logic error: file name %s inconsistent with expected index %d' % (file, i)
            roi_sources = p['sources']
            for key,item in roi_sources.items():
                if key in self.extended_catalog.names: continue
                skydir = item['skydir']
                if self.update_positions is not None:
                    ellipse = item.get('ellipse', None)
                    ts = item['ts']
                    if ellipse is not None and not np.any(np.isnan(ellipse)) :
                        fit_ra, fit_dec, a, b, ang, qual, delta_ts = ellipse
                        if qual<5 and a < 0.2 and \
                                ts>self.update_positions and delta_ts>0.2:
                            skydir = SkyDir(float(fit_ra),float(fit_dec))
                            moved +=1
                ps = sources.PointSource(name=self.rename_source(key), 
                    skydir=skydir, model= item['model'],
                    ts=item['ts'],band_ts=item['band_ts'], index=index)
                if self.free_index is not None and not ps.free[1] and ps.ts>self.free_index:
                        ps.free[1]=True
                        print 'Freed photon index for source %s'%ps.name
                if sources.validate(ps,self.nside, self.filter):
                    self._check_position(ps) # check that it is not coincident with previous source(warning for now?)
                    self.point_sources.append( ps)
            # make a list of extended sources used in the model   
            t = []
            names = p.get('diffuse_names', self.diffuse )
            for name, model in zip(names, p['diffuse']):
                if '_p' not in model.__dict__:
                    model.__dict__['_p'] = model.__dict__.pop('p')  # if loaded from old representation
                key = name.split('_')[0]
                if key in self.diffuse_dict:
                    #if model[0]<1e-2:
                    #    model[0]=1e-2
                    #print 'SkyModel warning: reset norm to 1e-2 for %s' % name
                    t.append(sources.GlobalSource(name=name, model=model, skydir=None, index=index))
                else:
                    es = self.extended_catalog.lookup(name)
                    if es is None:
                        #raise Exception( 'Extended source %s not found in extended catalog' %name)
                        print 'SkyModel warning: Extended source %s not found in extended catalog, removing' %name
                        continue
                    if self.hpindex(es.skydir)!=index: continue
                    
                    if es.model.name!=model.name:
                        if name not in self.changed:
                            print 'SkyModel warning: catalog model %s changed from %s for %s'% (es.model.name, model.name, name)
                        self.changed.add(name)
                    else:
                        es.model=model #update with fit values
                    if sources.validate(es,self.nside, lambda x: True): 
                        self.extended_sources.append(es)
            self.global_sources.append(t)
        # check for new extended sources not yet in model
        self._check_for_extended()
        if self.update_positions and moved>0:
            print 'updated positions of %d sources' % moved
 
    def _check_for_extended(self):
        if self.__dict__.get('extended_catalog') is None: return
        for name in self.extended_catalog.names:
            if name.replace(' ','') not in [g.name.replace(' ','') for g in self.extended_sources]:
                print 'extended source %s added to model' % name
                self.extended_sources.append(self.extended_catalog.lookup(name))
    def _check_position(self, ps):
        if self.closeness_tolerance<0.: return
        for s in self.point_sources:
            delta=np.degrees(s.skydir.difference(ps.skydir))
            if delta<self.closeness_tolerance:
                print  'SkyModel warning: appended source %s %.2f %.2f is %.2f deg (<%.2f) from %s (%d)'\
                    %(ps.name, ps.skydir.ra(), ps.skydir.dec(), delta, self.closeness_tolerance, s.name, s.index)
        
    #def skydir(self, index):
    #    return Band(self.nside).dir(index)
    def hpindex(self, skydir):
        return Band(self.nside).index(skydir)
    
    def _select_and_freeze(self, sources, src_sel):
        """ 
        sources : list of Source objects
        src_sel : selection object
        -> list of selected sources selected by src_sel.include, 
            with some frozen according to src_sel.frozen
            order so the free are first
        """
        inroi = filter(src_sel.include, sources)
        for s in inroi:
            #s.freeze(src_sel.frozen(s))
            s.model.free[:] = False if src_sel.frozen(s) else s.free
        return filter(src_sel.free,inroi) + filter(src_sel.frozen, inroi)
    
    def get_point_sources(self, src_sel):
        """
        return a list of PointSource objects appropriate for the ROI
        """
        return self._select_and_freeze(self.point_sources, src_sel)
        
    def get_diffuse_sources(self, src_sel):
        """return diffuse, global and extended sources defined by src_sel
            always the global diffuse, and perhaps local extended sources.
            For the latter, make parameters free if not selected by src_sel.frozen
            TODO: feature to override free selection for globals.
        """
        globals = self.global_sources[self.hpindex(src_sel.skydir())]
        for s in globals:
            dfile = os.path.expandvars(os.path.join('$FERMI','diffuse', s.name))
            assert os.path.exists(dfile), 'file %s not found' % dfile
            prefix = s.name.split('_')[0]
            filename, dmodel = self.diffuse_dict[prefix]
            s.dmodel = [dmodel]
            s.name = os.path.split(filename)[-1]
            s.smodel = s.model
            if '_p' not in s.model.__dict__:
                s.model.__dict__['_p'] = s.model.__dict__.pop('p')  # if loaded from old representation

        extended = self._select_and_freeze(self.extended_sources, src_sel)
        for s in extended: # this seems redundant, but was necessary
            s.model.free[:] = False if src_sel.frozen(s) else s.free
            sources.validate(s,self.nside, None)
            s.smodel = s.model
            
        return globals, extended

    def toXML(self,filename, ts_min=None, title=None):
        """ generate a file with the XML version of the sources in the model
        """
        catrec = self.source_rec()
        point_sources = self.point_sources if ts_min is None else filter(lambda s: s.ts>ts_min, self.point_sources)
        from uw.utilities import  xml_parsers # isolate this import, which brings in full pointlike
        stacks= [
            xml_parsers.unparse_diffuse_sources(self.extended_sources,True,False,filename),
            xml_parsers.unparse_point_sources(point_sources,strict=True),
        ]
        xml_parsers.writeXML(stacks, filename, title=title)

    def write_reg_file(self, filename, ts_min=None, color='green'):
        """ generate a 'reg' file from the catalog, write to filename
        """
        catrec = self.source_rec()
        have_ellipse = 'Conf_95_SemiMajor' in catrec.dtype.names #not relevant: a TODO
        out = open(filename, 'w')
        print >>out, "# Region file format: DS9 version 4.0 global color=%s" % color
        rec = catrec if ts_min is  None else catrec[catrec.ts>ts_min]
        for s in rec:
            if have_ellipse:
                print >>out, "fk5; ellipse(%.4f, %.4f, %.4f, %.4f, %.4f) #text={%s}" % \
                                (s.ra,s,dec,
                                  s.Conf_95_SemiMinor,Conf_95_SemiMajor,Conf_95_PosAng,
                                  s.name)
            else:
                print >> out, "fk5; point(%.4f, %.4f) # point=cross text={%s}" %\
                                (s.ra, s.dec, s.name)
        out.close()

    def _load_recfiles(self, reload=False):
        """ make a cache of the recarray summary """
        recfiles = map(lambda name: os.path.join(self.folder, '%s.rec'%name) , ('rois','sources'))
        if reload or not os.path.exists(recfiles[0]):
            catrec.create_catalog(self.folder, save_local=True, ts_min=5)
        self.rois,self.sources = map( lambda f: pickle.load(open(f)), recfiles)
        print 'loaded %d rois, %d sources' % (len(self.rois), len(self.sources))

    def roi_rec(self, reload=False):
        self._load_recfiles(reload)
        return self.rois
    def source_rec(self, reload=False):
        self._load_recfiles(reload)
        return self.sources
    def add_limb(self, scale=1e-3, mindec=45):
        from uw.like import Models
        con = Models.Constant(p=[scale])
        t = sources.GlobalSource(name='limb_cube_v0.fits', model=con, skydir=None)
        cnt=0
        for index in range(1728):
            gs = self.global_sources[index]
            if len(gs)==3: continue # if 3, already added
            if np.abs(Band(self.nside).dir(index).dec())<mindec: continue
            gs.append(sources.GlobalSource(name='limb_cube_v0.fits', model=con, skydir=None))
            cnt+=1
        if cnt>0: print 'Added the limb to %d rois above abs(dec)=%.1f' % (cnt, mindec)

    
    
class SourceSelector(object):
    """ Manage inclusion of sources in an ROI."""
    
    defaults = (
        ('max_radius',10,'Maximum radius (deg.) within which sources will be selected.'),
        ('free_radius',3,'Radius (deg.) in which sources will have free parameters'),
    )
    iteration =0
    @keyword_options.decorate(defaults)
    def __init__(self, skydir, **kwargs):
        self.mskydir = skydir
        keyword_options.process(self,kwargs)
        self.name='ROI#04d' % iteration
        self.iteration += 1
    
    def name(self):
        return 'ROI#04d' % iteration

    def near(self,source, radius):
        return source.skydir.difference(self.mskydir)< np.radians(radius)

    def include(self,source):
        """ source -- an instance of Source """
        return self.near(source, self.max_radius)

    def free(self,source):
        """ source -- an instance of Source """
        return self.near(source, self.free_radius)

    def frozen(self,source): return not self.free(source)

    def skydir(self): return self.mskydir
        
class HEALPixSourceSelector(SourceSelector):
    """ Manage inclusion of sources in an ROI based on HEALPix.
    Overrides the free method to define HEALpix-based free regions
    """

    nside=12 # default, override externally
    @keyword_options.decorate(SourceSelector.defaults)
    def __init__(self, index, **kwargs):
        """ index : int
                HEALpix index for the ROI (RING)
            nside : int
                HEALPix nside parameter
        """
        keyword_options.process(self,kwargs)
        self.myindex = index
        self.mskydir =  self.skydir(index)

    def name(self):
        return 'HP%02d_%04d' % (self.nside, self.myindex)

    def skydir(self, index=None):
        return Band(self.nside).dir(index) if index is not None else self.mskydir
        
    def index(self, skydir):
        return Band(self.nside).index(skydir)
    
    def free(self,source):
        """
        source : instance of skymodel.Source
        -> bool, if this source in in the region where fit parameters are free
        """
        return self.index(source.skydir) == self.myindex
        
class Rename(object):
    """ functor class to rename sources
        pass as object:
        SkyModel( ..., rename_source=Rename(s,'tset'),...)
    """
    def __init__(self, prefix, srec):
        self.srec= srec.copy()
        self.srec.sort(order='ra')
        self.names = list(self.srec.name[-self.srec.extended])
        self.prefix=prefix
        print 'found %d names to convert' % len(self.names)
        
    def __call__(self, name):
        """ name: string, name to convert"""
        try:
            return '%s%04d' %(self.prefix,self.names.index(name))
        except:
            return name

class RemoveByName(object):
    """ functor to remove sources, intended to be a filter for SkyModel"""
    def __init__(self, names):
        """ names : string or list of strings
            if a string, assume space-separated set of names (actually works for a single name)
        """
        tnames = names.split() if type(names)==types.StringType else names
        self.names = map( lambda x: x.replace('_', ' '), tnames)
    def __call__(self,ps):
        name = ps.name.strip().replace('_', ' ')
        return name not in self.names
    
class UpdatePulsarModel(object):
    """ special filter to replace models if necessary"""
    def __init__(self, infile=None, tol=0.2):
        import pyfits
        self.tol=tol
        if infile is None:
            infile = os.path.expandvars(os.path.join('$FERMI','catalog','srcid', 'cat','obj-pulsar-lat_v450.fits')) 
        self.data = pyfits.open(infile)[1].data
        self.sdir = map(lambda x,y: SkyDir(float(x),float(y)), self.data.field('RAJ2000'), self.data.field('DEJ2000'))
        self.names = self.data.field('Source_Name')
        self.tags = [False]*len(self.data)
    def __call__(self, s):
        sdir = s.skydir
        for i,t in enumerate(self.sdir):
            if np.degrees(t.difference(sdir))<self.tol:
                self.tags[i]=True
                if s.model.name=='ExpCutoff': return True
                flux = s.model[0]
                if flux>1e-18:
                    print 'Skymodel: replacing model for: %s(%d): pulsar name: %s' % (s.name, s.index, self.names[i]) 
                    s.model = Models.ExpCutoff()
                    s.free = s.model.free.copy()
                else:
                    print 'Apparent pulsar %s(%d), %s, is very weak, flux=%.2e <1e-13: leave as powerlaw' % (s.name, s.index, self.names[i], flux)
                break
        if s.model.name=='ExpCutoff':
            print 'Skymodel setup warning: %s (%d) not a pulsar, should not be expcutoff' % (s.name, s.index)
        return True
    def summary(self):
        n = len(self.tags)-sum(self.tags)
        if n==0: return
        print 'did not find %d sources ' % n
        for i in range(len(self.tags)):
            if not self.tags[i]: print '%s %9.3f %9.3f ' % (self.names[i], self.sdir[i].ra(), self.sdir[i].dec())
     
class MultiFilter(list):
    """ filter that is a list of filters """
    def __init__(self, filters):
        """ filters : list
                if an element of the list is a string, evaluate it first
        """
        for filter in filters: 
            if type(filter)==types.StringType:
                filter = eval(filter)
            self.append(filter)
            
                
    def __call__(self, source):
        for filter in self:
            if not filter(source): return False
        return True
