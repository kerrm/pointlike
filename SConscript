# -*- python -*-
# @file SConscript
# @brief scons build specifications
#
# $Header: /nfs/slac/g/glast/ground/cvs/pointlike/SConscript,v 1.13 2008/07/01 00:30:35 glastrm Exp $
# Authors: Toby Burnett <tburnett@u.washington.edu>
# Version: pointlike-06-02-04

#specify package name, applications
package= 'pointlike'
apps   =['pointfit', 'pointfind', 'alignment']

# this part is standard: assume includes, a shareable lib, zero or more applications, a test program
Import('baseEnv')
Import('listFiles')
progEnv = baseEnv.Clone()
libEnv = baseEnv.Clone()

libEnv.Tool(package+'Lib', depsOnly = 1)
progEnv.Tool(package+'Lib')
progEnv.Tool('registerObjects', 
    package  = package, 
    includes = listFiles([package+'/*.h']),
    libraries= [
        libEnv.SharedLibrary(package, listFiles(['src/*.cxx']))], 
    binaries = [progEnv.Program(name, listFiles(['src/%s/*.cxx'%name])) for name in apps], 
    testApps = [progEnv.Program('test_'+package, listFiles(['src/test/*.cxx']))],
 )
