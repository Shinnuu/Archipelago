"""A small R3000 assembler for the patch's hand-written routines.

X5 learned both of its hardest lessons here: a hand-typed hex word that
encoded s3 where s1 was meant, and the R3000 LOAD DELAY SLOT - a loaded value
is not available to the very next instruction, so `lbu t4, X` / `sb t4, Y`
stores the PREVIOUS t4. So routines are written as assembly text, encoded
field by field, and `assemble` refuses any load whose next instruction reads
the loaded register, and any branch or jump sitting in another's delay slot.
"""
import re

REGS = {name: i for i, name in enumerate(
    "zero at v0 v1 a0 a1 a2 a3 t0 t1 t2 t3 t4 t5 t6 t7 "
    "s0 s1 s2 s3 s4 s5 s6 s7 t8 t9 k0 k1 gp sp fp ra".split())}

_I_ALU = {"addiu": 0x09, "slti": 0x0A, "sltiu": 0x0B, "andi": 0x0C, "ori": 0x0D, "xori": 0x0E}
_LOADS = {"lb": 0x20, "lh": 0x21, "lw": 0x23, "lbu": 0x24, "lhu": 0x25}
_STORES = {"sb": 0x28, "sh": 0x29, "sw": 0x2B}
_R3 = {"addu": 0x21, "subu": 0x23, "and": 0x24, "or": 0x25, "xor": 0x26, "nor": 0x27,
       "slt": 0x2A, "sltu": 0x2B, "sllv": 0x04, "srlv": 0x06}
_SHIFTS = {"sll": 0x00, "srl": 0x02, "sra": 0x03}
_BRANCH2 = {"beq": 0x04, "bne": 0x05}
_BRANCH1 = {"blez": 0x06, "bgtz": 0x07}
_TRANSFERS = {"j", "jal", "jr", "jalr", "beq", "bne", "blez", "bgtz", "beqz", "bnez", "b"}


def _reg(tok: str) -> int:
    tok = tok.strip().lstrip("$")
    if tok not in REGS:
        raise ValueError(f"unknown register {tok!r}")
    return REGS[tok]


def _imm(tok: str, labels: dict[str, int] | None = None) -> int:
    tok = tok.strip()
    if labels is not None and tok in labels:
        return labels[tok]
    return int(tok, 0)


def _mem(tok: str) -> tuple[int, int]:
    m = re.fullmatch(r"\s*(-?[0-9a-fA-Fx]+)?\s*\(\s*\$?(\w+)\s*\)\s*", tok)
    if not m:
        raise ValueError(f"bad memory operand {tok!r}")
    return int(m.group(1) or "0", 0), _reg(m.group(2))


def _s16(value: int, what: str) -> int:
    if not -0x8000 <= value <= 0xFFFF:
        raise ValueError(f"{what} {value:#x} does not fit 16 bits")
    return value & 0xFFFF


def _encode(mnem: str, ops: list[str], pc: int, labels: dict[str, int]) -> int:
    def branch(target: int) -> int:
        delta = target - (pc + 4)
        if delta % 4:
            raise ValueError(f"misaligned branch target {target:#x}")
        return _s16(delta // 4, "branch offset")

    if mnem == "nop":
        return 0
    if mnem == "lui":
        return (0x0F << 26) | (_reg(ops[0]) << 16) | _s16(_imm(ops[1]), "lui")
    if mnem in _I_ALU:
        rt, rs, imm = _reg(ops[0]), _reg(ops[1]), _imm(ops[2])
        return (_I_ALU[mnem] << 26) | (rs << 21) | (rt << 16) | _s16(imm, mnem)
    if mnem in _LOADS or mnem in _STORES:
        op = _LOADS.get(mnem, _STORES.get(mnem))
        offset, base = _mem(ops[1])
        return (op << 26) | (base << 21) | (_reg(ops[0]) << 16) | _s16(offset, "offset")
    if mnem in _R3:
        rd, rs, rt = (_reg(o) for o in ops)
        if mnem in ("sllv", "srlv"):          # sllv rd, rt, rs
            rs, rt = rt, rs
        return (rs << 21) | (rt << 16) | (rd << 11) | _R3[mnem]
    if mnem in _SHIFTS:
        rd, rt, sa = _reg(ops[0]), _reg(ops[1]), _imm(ops[2])
        if not 0 <= sa < 32:
            raise ValueError(f"shift {sa} out of range")
        return (rt << 16) | (rd << 11) | (sa << 6) | _SHIFTS[mnem]
    if mnem in _BRANCH2:
        return (_BRANCH2[mnem] << 26) | (_reg(ops[0]) << 21) | (_reg(ops[1]) << 16) \
            | branch(_imm(ops[2], labels))
    if mnem in ("beqz", "bnez"):
        op = 0x04 if mnem == "beqz" else 0x05
        return (op << 26) | (_reg(ops[0]) << 21) | branch(_imm(ops[1], labels))
    if mnem == "b":
        return (0x04 << 26) | branch(_imm(ops[0], labels))
    if mnem in _BRANCH1:
        return (_BRANCH1[mnem] << 26) | (_reg(ops[0]) << 21) | branch(_imm(ops[1], labels))
    if mnem in ("j", "jal"):
        target = _imm(ops[0], labels)
        if (target & 0xF0000000) != (pc & 0xF0000000) or target % 4:
            raise ValueError(f"{mnem} target {target:#x} unreachable from {pc:#x}")
        return ((0x02 if mnem == "j" else 0x03) << 26) | ((target >> 2) & 0x3FFFFFF)
    if mnem == "jr":
        return (_reg(ops[0]) << 21) | 0x08
    if mnem == "jalr":
        return (_reg(ops[0]) << 21) | (31 << 11) | 0x09
    raise ValueError(f"unsupported instruction {mnem!r}")


def _reads(mnem: str, ops: list[str]) -> set[int]:
    """Registers an instruction reads (for the load-delay audit)."""
    if mnem in ("nop", "lui", "j", "jal", "b"):
        return set()
    if mnem in _I_ALU or mnem in _BRANCH1 or mnem in ("beqz", "bnez"):
        return {_reg(ops[1])} if mnem in _I_ALU else {_reg(ops[0])}
    if mnem in _LOADS:
        return {_mem(ops[1])[1]}
    if mnem in _STORES:
        return {_reg(ops[0]), _mem(ops[1])[1]}
    if mnem in _R3:
        return {_reg(ops[1]), _reg(ops[2])}
    if mnem in _SHIFTS:
        return {_reg(ops[1])}
    if mnem in _BRANCH2:
        return {_reg(ops[0]), _reg(ops[1])}
    if mnem in ("jr", "jalr"):
        return {_reg(ops[0])}
    return set()


def _parse(source: str) -> list[tuple[str | None, str, list[str], str]]:
    """[(label, mnemonic, operands, source line)] - one entry per instruction
    or bare label."""
    out = []
    for raw in source.splitlines():
        line = raw.split(";")[0].strip()
        if not line:
            continue
        label = None
        if ":" in line:
            label, line = (part.strip() for part in line.split(":", 1))
        if not line:
            out.append((label, "", [], raw))
            continue
        mnem, _, rest = line.partition(" ")
        ops = [o.strip() for o in re.split(r",(?![^(]*\))", rest)] if rest.strip() else []
        out.append((label, mnem.lower(), ops, raw))
    return out


def assemble(source: str, base: int) -> list[int]:
    """Assemble `source` for load address `base`; returns the words."""
    lines = _parse(source)
    labels, pc = {}, base
    for label, mnem, _ops, _raw in lines:
        if label:
            if label in labels:
                raise ValueError(f"label {label!r} defined twice")
            labels[label] = pc
        if mnem:
            pc += 4
    words, pc, prev = [], base, None
    for label, mnem, ops, raw in lines:
        if not mnem:
            continue
        if prev is not None:
            p_mnem, p_ops, p_raw = prev
            if p_mnem in _LOADS and _reg(p_ops[0]) != 0 and _reg(p_ops[0]) in _reads(mnem, ops):
                raise ValueError(f"load delay hazard: {p_raw.strip()!r} then {raw.strip()!r}")
            if p_mnem in _TRANSFERS and mnem in _TRANSFERS:
                raise ValueError(f"transfer in a delay slot: {raw.strip()!r}")
        words.append(_encode(mnem, ops, pc, labels))
        prev = (mnem, ops, raw)
        pc += 4
    if prev is not None and prev[0] in _TRANSFERS:
        raise ValueError(f"routine ends on a transfer with no delay slot: {prev[2].strip()!r}")
    return words


def word(instruction: str, pc: int) -> int:
    """One instruction at `pc` - for a hook site, whose delay slot is the
    host's next word (so the routine-level checks do not apply)."""
    (_label, mnem, ops, _raw), = _parse(instruction)
    return _encode(mnem, ops, pc, {})


def to_bytes(words: list[int]) -> bytes:
    return b"".join(w.to_bytes(4, "little") for w in words)
