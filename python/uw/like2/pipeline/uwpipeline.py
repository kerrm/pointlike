"""
task UWpipeline Interface to the ISOC PipelineII

$Header: /nfs/slac/g/glast/ground/cvs/pointlike/python/uw/like2/pipeline/uwpipeline.py,v 1.5 2012/12/26 18:47:53 burnett Exp $
"""
import os, argparse
import numpy as np
from uw.like2.pipeline import check_data
from uw.like2.pipeline import pipeline_job
from uw.like2.pipeline import check_converge
from uw.like2.pipeline import diagnostic_plots, pipe

class StartStream(object):
    """ setup, start a stream """
    def main(self, args):
        pipeline='/afs/slac/g/glast/ground/bin/pipeline -m PROD createStream '
        for stage in args.stage:
            cmd=pipeline+' -D "stage=%s, SKYMODEL_SUBDIR=%s, job_list=%s" UWpipeline' \
                %(stage, args.skymodel,args.job_list)
            print '-->' , cmd
            if not args.test:
                os.system(cmd)

class Summary(object):
    def get_stage(self, args):
        stagelist = args.stage[0] 
        t = stagelist.split(':',1)
        if len(t)==2:
            stage, nextstage = t 
        else: stage,nextstage = t[0], None
        return stage
    def main(self, args):
        stage = self.get_stage(args)
        kw = stagenames[stage].get('sum', None)
        if kw is not None:
            diagnostic_plots.main(kw)
            
class JobProc(Summary):
    """ process args for running pipeline jobs"""
    def main(self, args):
        stage = self.get_stage(args)
        setup = stagenames[stage].setup()
        pipeline_job.main(setup)
   
class Proc(dict):
    def __init__(self, run, help='', **kwargs):
        """ run: class or module -- must have main function """
        super(Proc, self).__init__(self,  help=help, **kwargs)
        self.run = run

    def __call__(self, args):
        self.run.main(args)
 
procnames = dict(
    # proc names (except for start) generated by the UWpipeline task as stream executes
    # start actually launches a stream
    start      = Proc(StartStream(), help='start a stream'),
    check_data = Proc(check_data, help='check that required data files are present'),
    job_proc   = Proc(JobProc(),  help='run a parallel pipeline job'),
    check_jobs = Proc(check_converge, help='check for convergence, combine results, possibly submit new stream'),
    summary_plots= Proc(Summary(), help='Process summaries, need stage'),
    )
    
class Stage(dict):
    def __init__(self, proc, pars, help='', **kwargs):
        super(Stage,self).__init__(proc=proc, pars=pars, help=help, **kwargs)
    def setup(self):
        return self['proc'](**self['pars'])

stagenames = dict(
    # List of possible stages, with proc to run, parameters for it,  summary string
    # list is partly recognized by check_converge.py, TODO to incoprorate it here, especially the part that may start a new stream
    create     =  Stage(pipe.Create, {}, sum='counts', help='Create a new skymodel'),
    update_full =  Stage(pipe.Update, dict( dampen=1.0,),sum='counts',help='perform update' ),
    update      =  Stage(pipe.Update, dict( dampen=0.5,),sum='counts',help='perform update' ),
    update_beta =  Stage(pipe.Update, dict( dampen=1.0, fix_beta=True),sum='counts',help='perform update', ),
    update_pivot=  Stage(pipe.Update, dict( dampen=1.0, repivot=True), sum='counts',help='update pivot', ), 
    finish      =  Stage(pipe.Finish, {}, sum='sources diffuse',help='perform localization', ),
    tables      =  Stage(pipe.Tables, {}, help='create tables',),
    sedinfo     =  Stage(pipe.Update, dict( processor='processor.full_sed_processor',sedfig_dir='"sedfig"',), sum='fb', ),
    diffuse     =  Stage(pipe.Update, dict( processor='processor.roi_refit_processor'), sum='gal', ),
    isodiffuse  =  Stage(pipe.Update, dict( processor='processor.iso_refit_processor'), sum='iso', ),
    limb        =  Stage(pipe.Update, dict( processor='processor.limb_processor'), sum='limb', ),
    fluxcorr    =  Stage(pipe.Update, dict( processor='processor.flux_correlations'), sum='fluxcorr', ),
    fluxcorrgal =  Stage(pipe.Update, dict( processor='processor.flux_correlations'), sum='flxcorriso', ),
    fluxcorriso =  Stage(pipe.Update, dict( processor='processor.flux_correlations(diffuse="iso*", fluxcorr="fluxcorriso")'), ),
    pulsar_table=  Stage(pipe.PulsarLimitTables, {}),
    localize    =  Stage(pipe.Update, dict( processor='processor.localize(emin=1000.)'), help='localize with energy cut' ),
) 
keys = stagenames.keys()
stage_help = 'stage name, or sequential stages separaged by : must be one of %s' %keys

def check_environment(args):
    if 'SKYMODEL_SUBDIR' not in os.environ:
        os.environ['SKYMODEL_SUBDIR'] = os.getcwd()
    else:
        os.chdir(os.environ['SKYMODEL_SUBDIR'])
    cwd = os.getcwd()
    assert os.path.exists('config.txt'), 'expect this folder (%s) to have a file config.txt'%cwd
    m = cwd.find('skymodels')
    assert m>0, 'did not find "skymodels" in path to cwd, which is %s' %cwd
    if args.stage[0] is None :
        pass #    raise Exception( 'No stage specified: either command line or os.environ')
    else:
        os.environ['stage']=args.stage[0]

    # add these to the Namespace object for convenience
    args.__dict__.update(skymodel=cwd, pointlike_dir=cwd[:m])

def check_names(stage, proc):
    if len(stage)==0:
        if proc is  None:
            raise Exception('No proc or stage argement specified')
        if proc not in procnames:
            raise Exception('proc name "%s" not in list %s' % (proc, procnames,keys()))
        return
    if stage[0] is None: 
        raise Exception('no stage specified')
    for s in stage:
        for t in s.split(':'):
            if t not in keys:
                raise Exception('"%s" not found in possible stage names, %s' %(t, keys))

def main( args ):
    check_environment(args)
    check_names(args.stage, args.proc)
    proc = args.proc
    print '--> %s for %s'%(proc, args.stage)
    procnames[proc](args)

if __name__=='__main__':
    parser = argparse.ArgumentParser(description=' start a UWpipeline stream, or run a proc; ')
    parser.add_argument('stage', nargs='*', default=[os.environ.get('stage', None)], help=stage_help)
    parser.add_argument('-p', '--proc', default=os.environ.get('PIPELINE_PROCESS', 'start'),
        help='proc name as defined by the UWpipeline xml, one of: %s'%procnames.keys())
    parser.add_argument('--job_list', default=os.environ.get('job_list', 'joblist.txt'), help='file used to allocate jobs')
    parser.add_argument('--stream', default=os.environ.get('PIPELINE_STREAM', -1), help='pipeline stream number')
    parser.add_argument('--test', action='store_true', help='Do not run' )
    args = parser.parse_args()
    main(args)
    
 
