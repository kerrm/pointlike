"""
Diffuse fitting analysis

"""

import os, glob, pickle
import numpy as np
import pylab as plt
import pandas as pd
from  matplotlib import (patches, gridspec)
from skymaps import SkyDir 
from . import (roi_info,  analysis_base)
from .. import (tools, configuration, response, diffuse)
from ..pipeline import stream

class DiffuseFits(roi_info.ROIinfo):
    """<b>Diffuse fit plots</b>
    <p>
    """
    def setup(self,**kwargs):
        super(DiffuseFits, self).setup()
        self.plotfolder = 'diffuse_fits'
        if not hasattr(self, 'energy'):
            self.energy = np.logspace(2.125, 5.875, 16)
    def summary(self):
        """Summary
        <pre>%(logstream)s</pre>
        """
        self.galfits=self.isofits=None
        galdict = self.config.diffuse['ring'] 
        self.galfile = galdict['filename'].split('/')[-1]
        if galdict.get('key', None) == 'gal':
            self.galcorr = None
        else:
            self.galcorr =galdict['correction']
        # Find streams 
        model = '/'.join(os.getcwd().split('/')[-2:])
        streamdf= pd.DataFrame(stream.StreamInfo(model)).T
        self.startlog()
        if os.path.exists('isotropic_fit'):
            # process isotrop
            files = sorted(glob.glob('isotropic_fit/*.pickle'))
            if len(files)>0:
                if len(files)<1728:
                    msg= "found {} files, expected 1728".format(len(files))
                    print msg
                    raise Exception(msg)
                self.isofits = np.array([pickle.load(open(f)) for f in files]);
                snum=streamdf.query('stage=="fitisotropic"').index[-1]
                print 'loaded iso fits, generated by stream {} at {}'.format(snum,streamdf.loc[snum].date )
     
        if os.path.exists('galactic_fit'):
            files = sorted(glob.glob('galactic_fit/*.pickle'))
            if len(files)>0:
                if len(files)<1728:
                    msg= "found {} files, expected 1728".format(len(files))
                    print msg
                    ids= map(lambda f: int(f.split('.')[-2][-4:]), files);
                    print np.array(sorted(list(set(range(1728)).difference(set(ids)))))
                    print 'trying to continue...'
                    #raise Exception(msg)

                self.galfits = np.array([pickle.load(open(f)) for f in files]); 
                snum=streamdf.query('stage=="fitgalactic" or stage=="postfitgalactic"').index[-1]
                print 'loaded gal fits, generated by stream {} at {}'.format(snum,streamdf.loc[snum].date )
        
        # get current isotropic template and values at energies
        self.iso=diffuse.diffuse_factory(self.config.diffuse['isotrop'])
        print 'isotropic:\n {}'.format(self.iso)
        self.isoflux = np.array([np.array(map(lambda e: self.iso[i](None, e), self.energy)) for i in range(2)])
        
        # and current galactic 
        self.gal=diffuse.diffuse_factory(self.config.diffuse['ring'])
        print 'galactic:\n{}'.format(self.gal)
        self.logstream= self.stoplog()

    def correction_plots(self, cc, vmin=0.5, vmax=1.5, title=None, hist=False):
        if isinstance(cc, pd.DataFrame):
            cc = cc.as_matrix()
        assert cc.shape[1]==8, 'Found shape {}'.format(cc.shape)
        if title is None:
            title = 'Galactic adjustments to: {}'.format(self.galcorr)
        if hist:
            hkw=dict(bins=np.linspace(vmin,vmax, 21), lw=1, histtype='step')
            fig,axx = plt.subplots(2,4, figsize=(14,7), sharex=True, sharey=False)
            plt.subplots_adjust(wspace=0.3)
        else:
            fig, axx = plt.subplots(2,4, figsize=(16,8), sharex=True, sharey=True)
            plt.subplots_adjust(left=0.10, wspace=0.1, hspace=0.1,right=0.92, top=0.92)
        for i,ax in enumerate(axx.flatten()):
            if hist:
                h = cc[:,i]
                ax.hist(h.clip(vmin, vmax),  **hkw)
                ax.axvline(1.0, color='grey', ls='--')
                mypatch= patches.Patch(fill=False,lw=0, facecolor='none', 
                    label='{:4.1f} {:4.1f}'.format(100*(h.mean()-1),100*h.std()),)
                ax.legend(handles=[mypatch], facecolor='none', edgecolor='none')
            else:
                t,scat=self.skyplot(cc[:,i],ax=ax, vmin=vmin, vmax=vmax, title='{:0f}'.format(self.energy[i]),
                        cmap=plt.get_cmap('coolwarm'), colorbar=False,labels=False);
            ax.set_title('{:.0f} MeV'.format(self.energy[i]))
        if not hist: 
            cbax = fig.add_axes((0.94, 0.15, 0.015, 0.7) )
            fig.colorbar(scat, cbax, orientation='vertical').set_label('correction factor', fontsize=12)
        fig.suptitle(title, fontsize=14)
        return fig

    def corr_plot(self, c, ax=None, vmin=0.5, vmax=1.5, title=None, colorbar=True,cmap='coolwarm', **scatkw):
        """SkyPlot of fit or correction factors
        """
        assert c.shape==(1728,), 'Found shape {}'.format(c.shape)
        if ax is None:
            fig, ax = plt.subplots(figsize=(6,6))
        else: fig=ax.figure
        t,scat=self.skyplot(c,ax=ax, vmin=vmin, vmax=vmax,
                        cmap=cmap, colorbar=colorbar,labels=True, **scatkw)
        if title is not None:
            ax.set_title(title, fontsize=14)

    def galactic_fit_maps(self):
        """Galactic correction fits
        Results of normalization fits to adjust level of galactic diffuse flux
        """
        if self.galfits is None: return
        return self.correction_plots(self.galfits, title='Fit to {}'.format(self.galfile),vmin=0.98,vmax=1.02)
 
    def galactic_fit_hists(self):
        """Galactic correction fits
        """
        if self.galfits is None: return
        return self.correction_plots( self.galfits, title='Fit to {}'.format(self.galfile),vmin=0.98,vmax=1.02, hist=True)

    def write_spectral_cube(self):
        gf = self.galfits
        scube = [hpm.HParray('',gf[:,i] ).getcol(nside=128) for i in range(8)]
        sm = hpm.HEALPixSkymap(np.array(scube).T, self.energy[:8])
        sm.write(self.galfile.replace('.fits', '_corrections.fits'))

    
    def all_plots(self):
         self.runfigures([
             self.summary,
             self.galactic_fit_maps,
             self.galactic_fit_hists,
        ])


def update_correction(self):
    """
    """
    diffuse_dir = os.path.expandvars('$FERMI/diffuse/')
    if self.galcorr is None:
        outfile=diffuse_dir+self.galfile.replace('.fits', '_corr.csv')
    else:
        i = self.galcorr.find('_corr')
        assert i>0, 'Check galcorr: expected to find "_corr"'
        #corr_version=
    #pd.DataFrame(self.galfits).to_csv(outfile)
    print 'wrote file {}'.format(outfile)
