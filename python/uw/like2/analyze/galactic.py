"""
Galactic diffuse plots

$Header: /nfs/slac/g/glast/ground/cvs/pointlike/python/uw/like2/analyze/galactic.py,v 1.1 2013/06/21 20:15:30 burnett Exp $

"""

import pandas as pd

from . import roi_info

class Galactic(roi_info.ROIinfo):
    def setup(self, **kw):
        super(Galactic, self).setup(**kw)
        self.plotfolder='gal'
        self.source_name='ring'
        self.title='Galactic'
        self.default_plots()
        
    def write_count_table(self, filename='galactic_counts.csv', modelnumber=0):
        s = [ x[1]['counts']['models'][modelnumber][1][:16] for x in self.df.iterrows()]
        u = pd.DataFrame(s, index=self.df.index)
        u.index.name='roiname'
        u.to_csv(filename)
        print 'wrote table of galactic diffuse counts to file %s' % filename
        
    def all_plots(self):
        super(Galactic, self).all_plots()