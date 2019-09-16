#! /usr/bin/env python
#
## Copyright (C) 2015-2018 Rolf Neugebauer.  All rights reserved.
## Copyright (C) 2015 Netronome Systems, Inc.  All rights reserved.
##
## Licensed under the Apache License, Version 2.0 (the "License");
## you may not use this file except in compliance with the License.
## You may obtain a copy of the License at
##
##   http://www.apache.org/licenses/LICENSE-2.0
##
## Unless required by applicable law or agreed to in writing, software
## distributed under the License is distributed on an "AS IS" BASIS,
## WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
## See the License for the specific language governing permissions and
## limitations under the License.

"""Run a set of PCIe micro-benchmarks on a NFP"""

import sys
from optparse import OptionParser

from pciebench.nfpbench import NFPBench
from pciebench.tablewriter import TableWriter
from pciebench.stats import histo2cdf
import pciebench.debug
import pciebench.sysinfo

def run_dbg_wr(nfp, win_sz, trans_sz,
               h_off, d_off, cache_flags, outdir):

    test_no = nfp.BW_DMA_WR
    twr = TableWriter(nfp.bw_fmt)
    twr.open(outdir + "dbg_bw", TableWriter.ALL)

    flags = cache_flags

    #if rnd:
    #    flags |= nfp.FLAGS_RANDOM

    nfp.bw_test(twr, test_no, flags, win_sz, trans_sz, h_off, d_off)
    twr.close(TableWriter.ALL)



def run_dbg_bw(nfp, wr_flag, rw_flag, win_sz, trans_sz,
               h_off, d_off, rnd, cache_flags, outdir):
    """Run bandwidth debug test"""

    if wr_flag and rw_flag:
        raise Exception("Illegal combination of flags")

    if wr_flag:
        test_no = nfp.BW_DMA_WR
    elif rw_flag:
        test_no = nfp.BW_DMA_RW
    else:
        test_no = nfp.BW_DMA_RD

    twr = TableWriter(nfp.bw_fmt)
    twr.open(outdir + "dbg_bw", TableWriter.ALL)

    flags = cache_flags

    if rnd:
        flags |= nfp.FLAGS_RANDOM

    nfp.bw_test(twr, test_no, flags, win_sz, trans_sz, h_off, d_off)
    twr.close(TableWriter.ALL)

def main():
    """Main function"""

    usage = """usage: %prog [options]"""

    parser = OptionParser(usage)
    parser.add_option('-f', '--fwfile',
                      default="../me/nfp6000_pciebench.nffw", action='store', metavar='FILE',
                      help='Firmware file to use')
    parser.add_option('-n', '--nfp',
                      default=0, action='store', type='int', metavar='NUM',
                      help='select NFP device')
    parser.add_option('-o', '--outdir',
                      default="./foo", action='store', metavar='DIRECTORY',
                      help='Directory where to write data files')
    parser.add_option('-u', '--user-helper', dest='helper',
                      default="../user/nfp-pciebench-helper", action='store', metavar='HELPER',
                      help='Path to helper binary')
    parser.add_option('-s', '--short',
                      action="store_true", dest='short', default=False,
                      help='Run a subset of the benchmarks')


    ##
    ## Debug options
    ##
    parser.add_option('--dbg-winsz', type='int',
                      default=4096, metavar='WINSZ', dest='dbg_winsz',
                      help='Debug: Transaction size (default 4096B)')
    parser.add_option('--dbg-sz', type='int',
                      default=8, metavar='TRANSSZ', dest='dbg_transsz',
                      help='Debug: Transaction size (default 8B)')

    parser.add_option('--dbg-hoff', type='int',
                      default=0, metavar='HOFF', dest='dbg_hoff',
                      help='Debug: Host offset (default 0)')
    parser.add_option('--dbg-doff', type='int',
                      default=0, metavar='DOFF', dest='dbg_doff',
                      help='Debug: Device offset (default 0)')

    #parser.add_option('--dbg-wrrd',
    #                  action="store_true", dest="dbg_lat_wrrd", default=False,
    #                  help='Debug LAT: Use write followed by read ' + \
    #                  '(default read)')
    #parser.add_option('--dbg-wr',
    #                  action="store_true", dest="dbg_bw_wr", default=False,
    #                  help='Debug BW: Use DMA writes (default read)')
    #parser.add_option('--dbg-rw',
    #                  action="store_true", dest="dbg_bw_rw", default=False,
    #                  help='Debug BW: Alternate between DMA read write')
    #parser.add_option('--dbg-rnd',
    #                  action="store_true", dest="dbg_rnd", default=False,
    #                  help='Debug: Random addressing (default sequential)')
    #parser.add_option('--dbg-long',
    #                  action="store_true", dest="dbg_long", default=False,
    #                  help='Debug: Do long run')
    #parser.add_option('--dbg-details',
    #                  action="store_true", dest="dbg_details", default=False,
    #                  help='Debug: Run the details test only')
    #parser.add_option('--dbg-cache',
    #                  default=None, metavar='CACHE', dest='dbg_cache',
    #                  help='Debug: Cache settings hwarm|dwarm|thrash ' + \
    #                       '(default None)')
    #parser.add_option('--dbg-mem',
    #                  action='store_true', dest='dbg_mem', default=False,
    #                  help='Debug: Hit the same cachelines over and over ' + \
    #                       '[window = transfersize] (default None)')

    parser.add_option("-v", '--verbose',
                      action="count", help='set the verbosity level')

    (options, _) = parser.parse_args()

    print(options)
    pciebench.debug.VLVL = options.verbose

    outdir = options.outdir
    if not outdir.endswith('/'):
        outdir += '/'

    # System information
    pciebench.sysinfo.collect(outdir, options.nfp)

    nfp = NFPBench(options.nfp, options.fwfile, options.helper)

    cache_vals = {'hwarm' : nfp.FLAGS_HOSTWARM,
                  'dwarm' : nfp.FLAGS_WARM,
                  'thrash' : nfp.FLAGS_THRASH}

    cache_flags = 0
    run_dbg_wr(nfp,
	   options.dbg_winsz, options.dbg_transsz,
	   options.dbg_hoff, options.dbg_doff,
	   cache_flags, outdir)
#    run_dbg_bw(nfp, options.dbg_bw_wr, options.dbg_bw_rw,
#	   options.dbg_winsz, options.dbg_transsz,
#	   options.dbg_hoff, options.dbg_doff,
#	   options.dbg_rnd, cache_flags, outdir)
    return

if __name__ == '__main__':
    sys.exit(main())
