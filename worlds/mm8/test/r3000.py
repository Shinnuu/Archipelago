"""A tiny R3000 interpreter for running the patch's routines in tests.

It decodes the ASSEMBLED WORDS (so it checks the encoder too) and models the
two things that bit X5: the branch delay slot, and the load delay slot - a
loaded value lands one instruction late, so a routine that reads it too
early sees the old value here exactly as it would on the console.
"""


class Halt(Exception):
    pass


class R3000:
    RETURN = 0xDEAD0000        # ra sentinel: a routine returning here stops the run

    def __init__(self):
        self.mem: dict[int, int] = {}
        self.r = [0] * 32
        self.r[31] = self.RETURN

    # ---- memory (little-endian bytes) ----
    def rb(self, a: int) -> int:
        return self.mem.get(a & 0xFFFFFFFF, 0)

    def wb(self, a: int, v: int) -> None:
        self.mem[a & 0xFFFFFFFF] = v & 0xFF

    def read(self, a: int, n: int) -> int:
        return sum(self.rb(a + i) << (8 * i) for i in range(n))

    def write(self, a: int, v: int, n: int) -> None:
        for i in range(n):
            self.wb(a + i, v >> (8 * i))

    def load_code(self, base: int, words: list[int]) -> None:
        for i, w in enumerate(words):
            self.write(base + 4 * i, w, 4)

    # ---- execution ----
    def run(self, pc: int, limit: int = 10_000) -> None:
        pending_load = None          # (reg, value) landing after the next instruction
        branch_to = None             # target taking effect after the delay slot
        for _ in range(limit):
            if pc == self.RETURN:
                return
            w = self.read(pc, 4)
            next_pc = pc + 4
            if branch_to is not None:
                next_pc, branch_to = branch_to, None
            land, pending_load = pending_load, None
            new_branch, new_load = self._step(w, pc)
            if land is not None and land[0]:
                self.r[land[0]] = land[1]
            if new_load is not None:
                pending_load = new_load
            self.r[0] = 0
            if new_branch is not None:
                branch_to = new_branch
            pc = next_pc
        raise Halt(f"no return within {limit} instructions")

    def _step(self, w: int, pc: int):
        op, rs, rt, rd = w >> 26, (w >> 21) & 31, (w >> 16) & 31, (w >> 11) & 31
        sa, fn, imm = (w >> 6) & 31, w & 0x3F, w & 0xFFFF
        simm = imm - 0x10000 if imm & 0x8000 else imm
        r, u32 = self.r, 0xFFFFFFFF
        if op == 0:
            if fn == 0x00: r[rd] = (r[rt] << sa) & u32
            elif fn == 0x02: r[rd] = r[rt] >> sa
            elif fn == 0x04: r[rd] = (r[rt] << (r[rs] & 31)) & u32         # sllv
            elif fn == 0x06: r[rd] = r[rt] >> (r[rs] & 31)                 # srlv
            elif fn == 0x08: return r[rs], None                          # jr
            elif fn == 0x21: r[rd] = (r[rs] + r[rt]) & u32
            elif fn == 0x23: r[rd] = (r[rs] - r[rt]) & u32
            elif fn == 0x24: r[rd] = r[rs] & r[rt]
            elif fn == 0x25: r[rd] = r[rs] | r[rt]
            elif fn == 0x26: r[rd] = r[rs] ^ r[rt]
            elif fn == 0x2B: r[rd] = int(r[rs] < r[rt])
            else: raise Halt(f"unsupported SPECIAL {fn:#x} at {pc:#x}")
            return None, None
        if op == 0x02: return (pc & 0xF0000000) | ((w & 0x3FFFFFF) << 2), None
        if op == 0x03:
            r[31] = pc + 8
            return (pc & 0xF0000000) | ((w & 0x3FFFFFF) << 2), None
        if op in (0x04, 0x05):
            taken = (r[rs] == r[rt]) == (op == 0x04)
            return ((pc + 4 + (simm << 2)) & u32 if taken else None), None
        if op == 0x09: r[rt] = (r[rs] + simm) & u32; return None, None
        if op == 0x0A:                                                   # slti: signed
            s = r[rs] - (1 << 32) if r[rs] & 0x80000000 else r[rs]
            r[rt] = int(s < simm)
            return None, None
        if op == 0x0B: r[rt] = int(r[rs] < (simm & u32)); return None, None
        if op == 0x0C: r[rt] = r[rs] & imm; return None, None
        if op == 0x0D: r[rt] = r[rs] | imm; return None, None
        if op == 0x0E: r[rt] = r[rs] ^ imm; return None, None
        if op == 0x0F: r[rt] = imm << 16; return None, None
        addr = (r[rs] + simm) & u32
        if op == 0x20:
            v = self.read(addr, 1); return None, (rt, (v - 0x100 if v & 0x80 else v) & u32)
        if op == 0x24: return None, (rt, self.read(addr, 1))
        if op == 0x25: return None, (rt, self.read(addr, 2))
        if op == 0x23:
            if addr % 4: raise Halt(f"unaligned lw {addr:#x} at {pc:#x}")
            return None, (rt, self.read(addr, 4))
        if op == 0x28: self.write(addr, r[rt], 1); return None, None
        if op == 0x29: self.write(addr, r[rt], 2); return None, None
        if op == 0x2B:
            if addr % 4: raise Halt(f"unaligned sw {addr:#x} at {pc:#x}")
            self.write(addr, r[rt], 4); return None, None
        raise Halt(f"unsupported opcode {op:#x} at {pc:#x}")
