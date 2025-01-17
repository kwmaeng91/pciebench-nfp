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

"""Main functions/class to control the NFP ME firmware"""

import subprocess
import struct
import math
import time

from .stats import ListStats
from .debug import err, warn, dbg, trc, log

# procfs files exported by the kernel module
_PROC_DMA_ADDRS = "/proc/pciebench_dma_addrs-%d"
_PROC_BUF_SZ = "/proc/pciebench_buf_sz-%d"
_PROC_BUFFER = "/proc/pciebench_buffer-%d"

# Symbol names for interacting with the FW
_NFP6000_ME_TEST_CTRL = "i32._test_ctrl"
_NFP6000_ME_TEST_PARAMS = "i32._test_params"
_NFP6000_ME_TEST_RESULT = "i32._test_result"
_NFP6000_ME_DMA_ADDRS = "i32._host_dma_addrs"
_NFP6000_TEST_JOURNAL = "test_journal"

_NFP3200_ME_TEST_CTRL = "cl1._test_ctrl"
_NFP3200_ME_TEST_PARAMS = "cl1._test_params"
_NFP3200_ME_TEST_RESULT = "cl1._test_result"
_NFP3200_ME_DMA_ADDRS = "cl1._host_dma_addrs"
_NFP3200_TEST_JOURNAL = "_test_journal"

_ME_TEST_CTRL = None
_ME_TEST_PARAMS = None
_ME_TEST_RESULT = None
_ME_DMA_ADDRS = None
_TEST_JOURNAL = None

# Firmware image name
FW_FILE = "./pciebench.fw"


def _exec_cmd(cmd):
    """Execute a command and return a tuple of return code and output"""
    trc(cmd)
    print(cmd)
    proc = subprocess.Popen(cmd, bufsize=16384, shell=True, close_fds=True,
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE)

    # wait for process to terminate
    res_data, _ = proc.communicate(None)
    ret = proc.returncode

    return ret, res_data

# Utility functions
# We have pretty good python support for accessing the NFP, but these
# are part of other packages.  Below we define a number of functions
# which are deliberately simple and cut corners in order to reduce
# dependencies on other package.

def _get_hwinfo(nfp_num):
    """Execute nfp-hwinfo and return the result as a dictionary"""
    ret = {}
    _, out = _exec_cmd("/opt/netronome/bin/nfp-hwinfo -n %d" % nfp_num)
    out = out.decode('ascii')
    lines = out.split('\n')
    for line in lines:
        line = line.strip()
        key, _, val = line.partition("=")
        ret[key] = val

    return ret

class _Symbol(object):
    """A struct, really"""
    def __init__(self, off, size):
        self.off = off
        self.size = size
        return

class NFPBench(object):
    """A class to interact the pciebench firmware"""

    # Tests (Keep this in sync with enum pciebench_tests in pciebench.h)
    BW_DMA_RD = 5
    BW_DMA_WR = 6
    BW_DMA_RW = 7

    TESTS = [BW_DMA_RD, BW_DMA_WR, BW_DMA_RW]

    TEST_NAMES = {BW_DMA_RD : "BW_DMA_RD",
                  BW_DMA_WR : "BW_DMA_WR",
                  BW_DMA_RW : "BW_DMA_RW",
                  }

    # Test flags
    FLAGS_WARM = 1 << 0       # Try to warm the window from the device
    FLAGS_THRASH = 1 << 1     # Try to thrash the cache from the device
    FLAGS_RANDOM = 1 << 2     # Random access, default sequential
    FLAGS_LONG = 1 << 3       # Do a longer run
    FLAGS_HOSTWARM = 1 << 31  # not a ME code flag
    FLAGS = FLAGS_WARM | FLAGS_THRASH | FLAGS_RANDOM | \
            FLAGS_LONG | FLAGS_HOSTWARM
    _FLAGS_CACHE = FLAGS_WARM | FLAGS_THRASH | FLAGS_HOSTWARM

    def __init__(self, nfp_num=0, fwfile=None, helper=None):
        """Initialise the class

        @nfp_num    NFP device number
        @fwfile     Path to firmware
        @helper     Optional path to a C helper program
        """

        global _ME_TEST_CTRL
        global _ME_TEST_PARAMS
        global _ME_TEST_RESULT
        global _ME_DMA_ADDRS
        global _TEST_JOURNAL

        self.nfp_num = nfp_num

        self.hwinfo = _get_hwinfo(self.nfp_num)
        self.freq_mhz = int(self.hwinfo['me.speed'])
        self.freq_hz = self.freq_mhz * 1000 * 1000

	self.nfp6000 = True
        #self.nfp6000 = self.hwinfo["chip.model"].startswith("NFP6") or \
        #               self.hwinfo["chip.model"].startswith("NFP4")

        _ME_TEST_CTRL = _NFP6000_ME_TEST_CTRL
        _ME_TEST_PARAMS = _NFP6000_ME_TEST_PARAMS
        _ME_TEST_RESULT = _NFP6000_ME_TEST_RESULT
        _ME_DMA_ADDRS = _NFP6000_ME_DMA_ADDRS
        _TEST_JOURNAL = _NFP6000_TEST_JOURNAL

        if fwfile:
            self.fw_name = fwfile
        else:
            self.fw_name = FW_FILE

        self.helper = helper

        self.symtab = {}
        return

    def cyc2ns(self, cycles):
        """Convert ME cycles to nanosecods"""
        return float(cycles) *  (1000 * 1000 * 1000) / self.freq_hz

    def _sym_write(self, sym, val):
        """Write value(s) to symbol"""
        _, _ = _exec_cmd("/opt/netronome/bin/nfp-rtsym -n %d %s %s" % (self.nfp_num, sym, val))
        return

    def _sym_read(self, sym, length=None):
        """Write value(s) to symbol"""
        if length:
            _, res_data = _exec_cmd("/opt/netronome/bin/nfp-rtsym -n %d -l %d -R %s" %
                                    (self.nfp_num, length, sym))
        else:
            _, res_data = _exec_cmd("/opt/netronome/bin/nfp-rtsym -n %d -R %s" %
                                    (self.nfp_num, sym))
        return res_data

    def _reload_fw(self):
        "Re-load the firmware image"
        subprocess.call("/opt/netronome/bin/nfp-nffw unload -n %d --ignore-debugger 2> /dev/null" %
                        self.nfp_num, shell=True)
        subprocess.call("/opt/netronome/bin/nfp-nffw %s load -n %d --ignore-debugger" %
                        (self.fw_name, self.nfp_num), shell=True)

        self._get_symtab()
        return

    def _get_symtab(self):
        """Extract some details from the symbol table from a fw file and
        return a dict, indexed by name and containing _Symbol objects"""

        # No need to re-read the symbol table on every FW load.
        if len(self.symtab):
            return
        _, out = _exec_cmd("/opt/netronome/bin/nfp-rtsym -n %d -L" % self.nfp_num)
        out = out.decode('ascii')
        for line in out.split("\n"):
            elems = line.split()
            if len(elems) == 0:
                continue
            if elems[0] == "Name":
                continue
            name = elems[0].strip()
            off = int(elems[2], 16)
            size = int(elems[3], 16)
            trc("%s 0x%08x 0x%08x" % (name, off, size))
            self.symtab[name] = _Symbol(off, size)
        return

    def _set_dma_addrs(self):
        """The kernel module exports a list of memory regions to be
        accessed by the NFP.  Read the list, validate it and write it
        to the NFP."""
        dma_addrs = []

        dbg("Using: %s" % (_PROC_DMA_ADDRS % self.nfp_num))
        inf = open(_PROC_DMA_ADDRS % self.nfp_num, 'r')
        for line in inf:
            addr = int(line, 0)
            dma_addrs.append(addr)
        inf.close()
        inf = open(_PROC_BUF_SZ % self.nfp_num, 'r')
        for line in inf:
            buf_sz = int(line)
        inf.close()

        # Sanity check (and debug)
        # The ME code makes some assumptions which we check here
        chunk_sz = buf_sz / len(dma_addrs)
        dbg("buf_sz=0x%x chunks=%d chunk_sz=0x%x" %
            (buf_sz, len(dma_addrs), chunk_sz))
        dbg("DMA addresses:")
        for start in dma_addrs:
            end = int(start + chunk_sz - 1)
            dbg("0x%x-0x%x" % (start, end))

            if start & (4096 -1):
                err("Start address 0x%x is not page aligned" % start)

            if not (start >> 29) == (end >> 29):
                err("Chunk 0x%x can't be addressed with a single c2p bar" %
                    start)

        loc_sym = self.symtab[_ME_DMA_ADDRS]
        entries = loc_sym.size / 8 # entries are 64bit
        nfp_addr = loc_sym.off

        entries = int(min(entries, len(dma_addrs)))

        val = ""
        for entry in range(0, entries):
            val += " 0x%x 0x%x" % (dma_addrs[entry] >> 32,
                                  dma_addrs[entry] & 0xffffffff)
            trc("Write DMA address 0x%x to 0x%x" %
                (dma_addrs[entry], nfp_addr))
        self._sym_write(_ME_DMA_ADDRS, val)
        return

    def _set_params(self, pm0, pm1, pm2, pm3, pm4):
        """Write the test parameters to the device"""
        loc_sym = self.symtab[_ME_TEST_PARAMS]
        val = "0x%x 0x%x 0x%x 0x%x 0x%x" % (pm0, pm1, pm2, pm3, pm4)
        trc("Write params to 0x%x -> %d %d %d %d %d (%s)" %
            (loc_sym.off, pm0, pm1, pm2, pm3, pm4, val))
        self._sym_write(_ME_TEST_PARAMS, val)
        return

    def _set_test_ctrl(self, ctrl):
        """Write the test control to device"""
        loc_sym = self.symtab[_ME_TEST_CTRL]
        val = "0x%x" % ctrl
        trc("Write test control to 0x%x" % loc_sym.off)
        self._sym_write(_ME_TEST_CTRL, val)
        return

    def _get_test_ctrl(self):
        """Get the test control value from the device"""
        loc_sym = self.symtab[_ME_TEST_CTRL]
        mem = self._sym_read(_ME_TEST_CTRL)
        # the symbol can be 8B or 4B depending where it is located
        if loc_sym.size == 8:
            res = struct.unpack('ii', mem)
        else:
            res = struct.unpack('i', mem)
        trc("Test Control: %s" % res)
        return res[0]

    def _get_result(self):
        """Get the result from the device
        returns time difference (in ME cycles) and a tuple of test results"""
        loc_sym = self.symtab[_ME_TEST_RESULT]
        mem = self._sym_read(_ME_TEST_RESULT)

        tmp = struct.unpack('<%uIc' % (loc_sym.size / 4), mem)
        trc("Test result: %s" % ' '.join([str(i) for i in tmp]))
        # first four words are time stamp
        start = (tmp[0] << 32) + tmp[1]
        end = (tmp[2] << 32) + tmp[3]
        diff = (end - start) * 16 # cycle counter every 16 cycles

        return diff, [tmp[4], tmp[5], tmp[6], tmp[7]]

    def _read_journal(self, name, count=None):
        """The ME code maintains two journals, one for test data and
        one fro debug purposes.  This internal functions reads up to
        @count values from the journal called @name.  If @count is
        None, the whole journal is returned."""

        loc_sym = self.symtab[name]

        if count == None:
            byte_cnt = loc_sym.size
        else:
            byte_cnt = min(loc_sym.size, count * 4)

        mem = self._sym_read(name, byte_cnt)
        res = struct.unpack('<%uIc' % (byte_cnt / 4), mem)
        return res[:-1]

    def get_journal(self, count=None, nullcheck=False):
        """Some tests uses a journal to store extra data.  This method
        reads that journal and returns a tuple of 32bit values up to
        @count if specified. If you expect the journal to be full and
        don't expect 0 values, use @nullcheck"""

        res = self._read_journal(_TEST_JOURNAL, count)

        if nullcheck:
            nullcount = 0
            for i in res:
                if i == 0:
                    nullcount += 1
            if not nullcount == 0:
                warn("journal countains %d null entries" % nullcount)
        return res

    def run_test(self, test_no, params, warm=0):
        """Run the test with @test_no and the provided parameters (a
        list/tuple).

        If @warm is set to a non-null value, the code will try to
        "warm" the cache with the first @warm bytes of the dma buffers
        by writing to them.

        Returns time difference (in ME cycles) and a tuple of test results
        """

	# Param0: cache flag(?), Param 1: size
        #param 2: window size (?), param 3: h_off? param 4: d_off?
        pm0 = 0
        pm1 = 0
        pm2 = 0
        pm3 = 0
        pm4 = 0
        if len(params) > 0:
            pm0 = params[0]
        if len(params) > 1:
            pm1 = params[1]
        if len(params) > 2:
            pm2 = params[2]
        if len(params) > 3:
            pm3 = params[3]
        if len(params) > 4:
            pm4 = params[4]

        dbg("Test: %d p0=%d p1=%d p2=%d p3=%d p4=%d" %
            (test_no, pm0, pm1, pm2, pm3, pm4))

        self._set_params(pm0, pm1, pm2, pm3, pm4)

        # If we have a C helper, use it
        cmd = self.helper + " -n %d -c %s -t %d -w %d" % \
	    (self.nfp_num, _ME_TEST_CTRL, test_no, warm)
        ret, _ = _exec_cmd(cmd)
        if not ret == 0:
	    err("Test helper failed with %d" % (ret))

        ret = self._get_test_ctrl()
        if ret < 0:
            err("Test %d failed with %d" % (test_no, ret))

        diff, res = self._get_result()
        log("Finished: cycles=%d res=%s" % (diff, res))

        return diff, res

    def dma_test(self, test_no, flags, win_sz, trans_sz, h_off, d_off):
        """Run a bandwidth test:
        @twr:      TableWriter object set up with @bw_fmt
        @test_no:  Test to run. One of @LAT_TESTS
        @flags:    Test flags. Combination of @FLAGS*
        @win_sz:   Window size to access
        @trans_sz: Transaction size
        @h_off:    Host offset (from the start of a 64B cache line)
        @d_off:    Device offset (from the start of a 64B cache line)

        Returns a list of individual latencies for further analysis
        """
        # Sanity checks
        if not test_no in self.TESTS:
            err("%s is not a bandwidth test" % test_no)
        if self.nfp6000 and (trans_sz > 4096):
            err("For NFP-6000 the transaction must be less than 4096")
        if win_sz % 64:
            err("Window size must be a multiple of 64. Was %d" % win_sz)
        if flags & ~self.FLAGS:
            err("Illegal flags %#08x (valid %#08x)" % (flags, self.FLAGS))
        if bin(flags & self._FLAGS_CACHE).count("1") > 1:
            err("Only one cache related flag may be set")

        cycles, res = self.run_test(
            test_no, [flags, trans_sz, win_sz, h_off, d_off],
            win_sz if flags & self.FLAGS_HOSTWARM else 0)

        return
