from collections import namedtuple
from enum import Enum
from dataclasses import dataclass


class Opcode(str, Enum):
    # ALU
    ADD = "add"
    SUB = "sub"
    MUL = "mul"
    DIV = "div"
    AND = "and"
    OR = "or"
    XOR = "xor"
    INV = "inv"

    # Stack
    DUP = "dup"
    DROP = "drop"
    SWAP = "swap"
    OVER = "over"
    PUSH_FLAGS = "push_flags"
    PUSH = "push"

    # Memory
    LOAD = "load"
    STORE = "store"

    # Control flow
    JUMP = "jump"
    JNZ = "jnz"
    CALL = "call"
    RET = "ret"

    # System / interrupts
    HALT = "halt"
    DI = "di"
    EI = "ei"
    IRET = "iret"

    def __str__(self):
        return str(self.value)
    

class Term(namedtuple("Term", "line pos word")):
    """
    Описание выражения из исходного текста программы.
    """


@dataclass
class Instruction:
    opcode: Opcode
    term: Term
    arg: int | None = None


opcode_to_binary = {
    # ALU
    Opcode.ADD: 0x01,
    Opcode.SUB: 0x02,
    Opcode.MUL: 0x03,
    Opcode.DIV: 0x04,
    Opcode.AND: 0x05,
    Opcode.OR:  0x06,
    Opcode.XOR: 0x07,
    Opcode.INV: 0x08,

    # Stack
    Opcode.DUP:         0x20,
    Opcode.DROP:        0x21,
    Opcode.SWAP:        0x22,
    Opcode.OVER:        0x23,
    Opcode.PUSH_FLAGS:  0x24,
    Opcode.PUSH:        0x25,

    # Memory
    Opcode.LOAD:  0x40,
    Opcode.STORE: 0x41,

    # Control flow
    Opcode.JUMP: 0x60,
    Opcode.JNZ:  0x61,
    Opcode.CALL: 0x62,
    Opcode.RET:  0x63,

    # System / interrupts
    Opcode.HALT: 0x80,
    Opcode.DI:   0x81,
    Opcode.EI:   0x82,
    Opcode.IRET: 0x83,
}

binary_to_opcode = {
    0x01: Opcode.ADD,
    0x02: Opcode.SUB,
    0x03: Opcode.MUL,
    0x04: Opcode.DIV,
    0x05: Opcode.AND,
    0x06: Opcode.OR,
    0x07: Opcode.XOR,
    0x08: Opcode.INV,

    0x20: Opcode.DUP,
    0x21: Opcode.DROP,
    0x22: Opcode.SWAP,
    0x23: Opcode.OVER,
    0x24: Opcode.PUSH_FLAGS,
    0x25: Opcode.PUSH,

    0x40: Opcode.LOAD,
    0x41: Opcode.STORE,

    0x60: Opcode.JUMP,
    0x61: Opcode.JNZ,
    0x62: Opcode.CALL,
    0x63: Opcode.RET,

    0x80: Opcode.HALT,
    0x81: Opcode.DI,
    0x82: Opcode.EI,
    0x83: Opcode.IRET,
}


def instr_size(instr: Instruction) -> int:
    return 5 if instr.arg is not None else 1


def to_bytes(code: list[Instruction]) -> bytes:
    """
    Преобразует машинный код в бинарное представление.
    """
    binary_bytes = bytearray()

    for instr in code:
        opcode_bin = opcode_to_binary[instr.opcode]
        binary_bytes.append(opcode_bin)

        if instr.arg is not None:
            binary_bytes.extend(instr.arg.to_bytes(4, byteorder="big", signed=True))

    return bytes(binary_bytes)


def to_hex(code: list[Instruction], base_addr: int = 0) -> str:
    """
    Преобразует машинный код в человекочитаемый HEX-вид.

    Формат:
    <address:dec> - <address:hex> - <HEXCODE> - <mnemonic>
    """
    result = []
    address = base_addr

    for instr in code:
        opcode_bin = opcode_to_binary[instr.opcode]
        instr_bytes = bytearray([opcode_bin])

        mnemonic = instr.opcode.value

        if instr.arg is not None:
            instr_bytes.extend(instr.arg.to_bytes(4, byteorder="big", signed=True))
            mnemonic = f"{mnemonic} {instr.arg}"

        hex_code = bytes(instr_bytes).hex(" ").upper()
        result.append(f"{address} - {address:08X} - {hex_code} - {mnemonic}")

        address += len(instr_bytes)

    return "\n".join(result)


def has_arg(opcode: Opcode) -> bool:
    return opcode in {
        Opcode.PUSH,
        Opcode.JUMP,
        Opcode.JNZ,
        Opcode.CALL,
    }


def from_bytes(binary_code: bytes, base_addr: int = 0) -> list[Instruction]:
    """
    Преобразует бинарное представление обратно в список инструкций.
    """
    code: list[Instruction] = []

    i = 0

    while i < len(binary_code):
        addr = base_addr + i
        opcode_bin = binary_code[i]

        if opcode_bin not in binary_to_opcode:
            raise ValueError(f"Unknown opcode 0x{opcode_bin:02X} at address 0x{addr:08X}")

        opcode = binary_to_opcode[opcode_bin]
        i += 1

        term = Term(0, addr, opcode.value)

        if has_arg(opcode):
            if i + 4 > len(binary_code):
                raise ValueError(f"Missing argument for {opcode.value} at address 0x{addr:08X}")

            arg = int.from_bytes(
                binary_code[i:i + 4],
                byteorder="big",
                signed=True,
            )

            code.append(Instruction(opcode=opcode, term=term, arg=arg))
            i += 4
        else:
            code.append(Instruction(opcode=opcode, term=term))

    return code
