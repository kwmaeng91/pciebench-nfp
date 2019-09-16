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

    # Reload fw
    nfp._reload_fw()
    # Set up a page
    # (currently, this is done separately)

    # Set dma addr to the ME
    # (currently, this uses the separately allocated page addrs)
    nfp._set_dma_addrs()

    while True:
        pass
    # Up to here is the real role of the server. From here, the ME has to
    # automatically initiate DMA from its side.
    # for testing purpose, however,
    # we can control DMA read / write with python.

    # Test DMA
    #test_no = nfp.BW_DMA_WR # RD / RW
    #flags = 0
    #nfp.dma_test(test_no, flags, options.dbg_winsz, options.dbg_transsz,
    #    options.dbg_hoff, options.dbg_doff)

    return

if __name__ == '__main__':
    sys.exit(main())
