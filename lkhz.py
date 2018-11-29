#!/usr/bin/env python
import time
import gzip
import datetime
import subprocess

'''
LKHZ is a class to dynamically calculate the CONFIG_HZ value for a running
Linux Kernel.

Additionally, you can use this class to convert a raw jiffies value into an
accurate datetime timestamp.
'''


class LKHZ():
    def __init__(self):
        self._hz = []
        self._count = 100
        self.config_hz = self._read_kernel_config_gz()

        self.offset = self.cpu0_offset
        self.last_since_boot = self.offset
        self._oavg = 0

    def _read_kernel_config_gz(self) -> int:
        _hz = None
        with gzip.open('/proc/config.gz') as f:
            for ln in f:
                if ln.startswith(b'CONFIG_HZ='):
                    _hz = ln.decode().split('=')[1]
                    _hz = int(_hz)
                    break

        return _hz

    def calibrate(self):
        for i in range(self._count):
            self._gv()

        self._oavg = self._avg
        self._start = int(time.time())

    @property
    def user_hz(self) -> int:
        # my testing has always resulted in a HZ value a fraction higher than
        # the integer value but we'll add 2 to be on the safe side
        return int(self.HZ+2 // 50*50)

    @property
    def cpu0_offset(self):
        # HRTIMER_BASE_BOOTTIME is index 2 of the clocks but this could
        # change so we search for the ktime_get_boottime identifier,
        # then get the nanosecond offset. cpu0 cannot be taken offline
        # afaik, so we'll use the first instance of boottime (each cpu
        # has a boottime)
        #
        # the offset changes whenever any form of suspend/resume occurs
        offset = 0
        with open('/proc/timer_list') as f:
            go = 2
            for line in f.readlines():
                if go == 2:
                    if line.endswith('ktime_get_boottime\n'):
                        go -= 1
                elif go == 1:
                    offset = int(line.strip().split(' ')[-2])
                    go = 0

                if not go:
                    break

        return offset/1000000000

    def jiffies_to_datetime(self, jiffies):
        # jiffies starts as -5min, then wraps
        adj_jiffies = jiffies + 300*self.user_hz
        if self.since_boot+self.cpu0_offset > 300:
            adj_jiffies -= (1 << 32)

        # the jiffies is now represented as seconds since boot
        jiffies_as_seconds_since_boot = adj_jiffies / self.config_hz

        # get the boot time and adjust for this offset
        with open('/proc/stat') as f:
            for line in f.readlines():
                if line.startswith('btime'):
                    btime = int(line.strip().split(' ')[1])

        ts = datetime.datetime.fromtimestamp(jiffies_as_seconds_since_boot
                                             + btime)

        return ts

    def _gv(self):
        _ = subprocess.check_output(['cat', '/proc/uptime', '/proc/timer_list']
                                    ).decode().split('\n')

        # why does scott need -16967.908 as well? it doesn't get suspended
        self.since_boot = float(_[0].split(' ')[0]) - self.offset

        # suspend/resume/pause event
        if abs(self.since_boot - self.last_since_boot) > 1:
            self.since_boot += self.offset
            self.offset = self.cpu0_offset
            self.since_boot -= self.offset

        self.last_since_boot = self.since_boot

        # there will be some variance between the times we read these files
        # due to the tiny overhead of file operations. that number should be
        # very small enough to ignore

        # /proc/timer_list is in raw jiffies. [almost] everything else in proc
        # /is jiffies/HZ
        for __ in _:
            if __.startswith('jiffies:'):
                self.jiffies = int(__.split(': ')[1])
                break

        # account for the -300 seconds that the jiffie counter starts at (and
        # wraps) as a side note; jiffie counter appears to be 64bit but is
        # actually two 32bit operations in the kernel done intelligently
        # because a 64bit memory read is considerably more expensive than a
        # 32bit read
        adj_jiffies = self.jiffies + 300*self.config_hz
        if self.since_boot > 300:
            adj_jiffies -= (1 << 32)

        self.HZ = round(adj_jiffies / self.since_boot, 8)
        self._hz.append(self.HZ)
        self._hz = self._hz[-1 * self._count:]
        self._avg = round(sum(self._hz)/len(self._hz), 8)
        if hasattr(self, '_min'):
            self._hz.append(self._min)
            self._hz.append(self._max)

        self._min = round(min(self._hz), 8)
        self._max = round(max(self._hz), 8)
        self._delta = self._max - self._min

    def analyze(self):
        print('\x1b[H\x1b[JCONFIG_HZ from /proc/config.gz indicates HZ is set'
              ' to {}'.format(self.config_hz))
        print('Running constant calculation of HZ, averages span'
              ' {} elements\n'.format(self._count))
        print('              seconds    calculated                            '
              '                        drift since')
        print('  jiffies    since boot    USER_HZ       min          avg      '
              '    max       variance    prg start'.format(self._count))
        print('\n\nrun time      cpu0_offset\n')

        while True:
            self._gv()
            _drift = self._avg-self._oavg
            _age = int(time.time()) - self._start

            print('\x1b[4A{:< 12} {:> 10.0f} {:<12.8f} {:<12.8f} {:<12.8f}'
                  .format(self.jiffies, self.since_boot, self.HZ, self._min,
                          self._avg), end='')
            print(' {:<12.8f} {:>8.8f} {:> 8.8f}'.format(
                self._max, self._delta, _drift))
            print('\n\n{:> 8}      {:>12.8f}'.format(_age, self.offset))
            time.sleep(0.02)


if __name__ == '__main__':
    # run forever calculating the CONFIG_HZ value and display values used to
    # obtain it
    hz = LKHZ()
    hz.analyze()
