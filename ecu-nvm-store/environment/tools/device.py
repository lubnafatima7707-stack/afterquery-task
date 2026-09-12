"""
Model of the internal NOR flash an ECU keeps its non volatile blocks in.

The device lives in the harness process, never in the process under test, so the
program being graded can only touch it through the line protocol and cannot
reach the operation counters, the erase counters or the image itself.

Page granularity: a page is programmed as a whole and only bits that are still
one can be driven to zero, so programming a page that is not erased leaves the
bitwise and of the old and new contents. An erase is issued on a whole sector,
takes the device away for a fixed number of ticks, and once a sector has been
erased more times than the part tolerates it starts leaving some pages holding
their old contents while still reporting the erase as done.
"""

ERASED_BYTE = 0xFF


class DeviceError(Exception):
    """An operation with arguments the device cannot accept."""


class Flash:
    def __init__(self, spec):
        self.sectors = int(spec["sectors"])
        self.pages_per_sector = int(spec["pages_per_sector"])
        self.page_bytes = int(spec["page_bytes"])
        self.t_read_ms = float(spec["t_read_ms"])
        self.t_program_ms = float(spec["t_program_ms"])
        self.erase_ticks = int(spec["erase_ticks"])
        weak = spec.get("weak_pages") or {}
        self.weak_pages = {int(k): sorted(int(p) for p in v) for k, v in weak.items()}
        self.weak_from = int(spec.get("weak_from", 1))
        blank = bytes([ERASED_BYTE]) * self.page_bytes
        self.image = [bytearray(blank) for _ in range(self.sectors * self.pages_per_sector)]
        self.erase_counts = [0] * self.sectors
        self.busy_until_tick = -1
        self.pending_erase = None
        self.n_read = 0
        self.n_program = 0
        self.n_erase = 0

    # ---------------------------------------------------------------- helpers

    def _slot(self, sector, page):
        if not (0 <= sector < self.sectors):
            raise DeviceError("sector %d out of range" % sector)
        if not (0 <= page < self.pages_per_sector):
            raise DeviceError("page %d out of range" % page)
        return sector * self.pages_per_sector + page

    def busy(self, tick):
        return tick < self.busy_until_tick

    def busy_ticks(self, tick):
        return max(0, self.busy_until_tick - tick)

    def settle(self, tick):
        """Finish an erase whose busy window has expired."""
        if self.pending_erase is not None and not self.busy(tick):
            self._finish_erase(self.pending_erase)
            self.pending_erase = None

    def _finish_erase(self, sector):
        keep = set()
        if self.erase_counts[sector] > self.weak_from:
            keep = set(self.weak_pages.get(sector, ()))
        base = sector * self.pages_per_sector
        blank = bytes([ERASED_BYTE]) * self.page_bytes
        for page in range(self.pages_per_sector):
            if page in keep:
                continue
            self.image[base + page] = bytearray(blank)

    # ------------------------------------------------------------ operations

    def read(self, tick, sector, page):
        slot = self._slot(sector, page)
        self.n_read += 1
        return bytes(self.image[slot]), self.t_read_ms

    def program(self, tick, sector, page, data):
        slot = self._slot(sector, page)
        if len(data) != self.page_bytes:
            raise DeviceError("a program takes exactly %d bytes, got %d"
                              % (self.page_bytes, len(data)))
        old = self.image[slot]
        self.image[slot] = bytearray(a & b for a, b in zip(old, data))
        self.n_program += 1
        return self.t_program_ms

    def erase(self, tick, sector):
        self._slot(sector, 0)
        self.erase_counts[sector] += 1
        self.n_erase += 1
        self.busy_until_tick = tick + self.erase_ticks
        self.pending_erase = sector
        return 0.0

    # ------------------------------------------- effects of losing the supply

    def cut_during_program(self, sector, page, data, fraction):
        """A program interrupted part way writes a prefix of the page."""
        slot = self._slot(sector, page)
        if len(data) != self.page_bytes:
            raise DeviceError("a program takes exactly %d bytes, got %d"
                              % (self.page_bytes, len(data)))
        written = int(fraction * self.page_bytes)
        old = self.image[slot]
        mixed = bytearray(old)
        for i in range(written):
            mixed[i] = old[i] & data[i]
        self.image[slot] = mixed
        self.n_program += 1

    def cut_during_erase(self, sector, fraction):
        """An abandoned erase clears a prefix of the sector and half clears one page."""
        base = self._slot(sector, 0)
        self.erase_counts[sector] += 1
        self.n_erase += 1
        done = int(fraction * self.pages_per_sector)
        blank = bytes([ERASED_BYTE]) * self.page_bytes
        for page in range(done):
            self.image[base + page] = bytearray(blank)
        if done < self.pages_per_sector:
            half = self.image[base + done]
            self.image[base + done] = bytearray(b | 0xF0 for b in half)

    def power_off(self):
        """A reset leaves the image alone; an erase in flight does not resume."""
        self.busy_until_tick = -1
        self.pending_erase = None
