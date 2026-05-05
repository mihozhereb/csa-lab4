import argparse
from enum import Enum
import logging
import re
import sys

from isa import Opcode, decode_instr


INTR_VECTOR_ADDR = 5
IN_ADDR = 9
OUT_ADDR = 13
WORD_SIZE = 4


class Memory:
    data: bytearray = None

    def __init__(self, memory: bytes):
        self.data = bytearray(memory)


class DataStack:
    data_stack_memory: list[int] = None

    def __init__(self):
        self.data_stack_memory: list[int] = []

    def tods(self) -> int:
        if len(self.data_stack_memory) < 1:
            raise RuntimeError("Data stack underflow: TODS requested from empty stack")

        return self.data_stack_memory[-1]

    def next(self) -> int:
        if len(self.data_stack_memory) < 2:
            raise RuntimeError("Data stack underflow: NEXT requested, stack has less than 2 values")

        return self.data_stack_memory[-2]

    def pop(self, value_from_alu: int = None) -> int:
        """
        Удаляет верхний элемент стека и смещает next => tods.
        Если установлен value_from_alu, то value_from_alu => tods, а значение next затирается.
        """
        if len(self.data_stack_memory) < 1:
            raise RuntimeError("Data stack underflow: pop from empty stack")

        res = self.data_stack_memory.pop()
        if value_from_alu is not None:
            if len(self.data_stack_memory) < 1:
                raise RuntimeError("Data stack underflow: cannot write ALU result after pop")

            self.data_stack_memory[-1] = value_from_alu
        return res
    
    def latch_tods(self, value_from_memory: int):
        """
        Заменяет верхний элемент на значение value_from_memory.
        """
        if len(self.data_stack_memory) < 1:
            raise RuntimeError("Data stack underflow: latch_tods on empty stack")

        self.data_stack_memory[-1] = value_from_memory

    def push(self, number: int):
        self.data_stack_memory.append(number)

    def swap(self):
        if len(self.data_stack_memory) < 2:
            raise RuntimeError("Data stack underflow: swap requires 2 values")

        self.data_stack_memory[-1], self.data_stack_memory[-2] = self.data_stack_memory[-2], self.data_stack_memory[-1]

    def over(self):
        if len(self.data_stack_memory) < 2:
            raise RuntimeError("Data stack underflow: over requires 2 values")

        self.data_stack_memory.append(self.data_stack_memory[-2])
    
    def dup(self):
        if len(self.data_stack_memory) < 1:
            raise RuntimeError("Data stack underflow: dup requires 1 value")

        self.data_stack_memory.append(self.data_stack_memory[-1])


class ReturnStack:
    data_stack_memory: list[int] = None

    def __init__(self):
        self.data_stack_memory: list[int] = []

    def tors(self) -> int:
        if len(self.data_stack_memory) < 1:
            raise RuntimeError("Return stack underflow: TORS requested from empty stack")

        return self.data_stack_memory[-1]
    
    def pop(self) -> int:
        if len(self.data_stack_memory) < 1:
            raise RuntimeError("Return stack underflow: pop from empty stack")

        return self.data_stack_memory.pop()

    def push(self, number: int):
        self.data_stack_memory.append(number)


class DataPath:
    memory: Memory = None
    "Память. Инициализируется входными данными конструктора."

    data_stack: DataStack = None
    "Стек данных."

    nzvc_register: int = None
    "Регистр флагов nzvc. Инициализируется нулём."

    input_buffer: list[tuple[int, int]] = None
    "Буфер входных данных. Инициализируется входными данными конструктора."

    output_buffer: list[int] = None
    "Буфер выходных данных."

    def __init__(self, memory: Memory, input_buffer: list[tuple[int, int]]):
        self.memory = memory
        self.data_stack = DataStack()
        self.nzvc_register = 0
        self.input_buffer = input_buffer
        self.output_buffer = []

    class SelNzvcIn(Enum):
        FROM_ALU = 1
        FROM_RS = 2

    def signal_latch_nzvc(self, sel: SelNzvcIn, flags: int = None):
        if sel == self.SelNzvcIn.FROM_ALU:
            self.nzvc_register = flags
        if sel == self.SelNzvcIn.FROM_RS:
            self.nzvc_register = flags

    class SelMemAdrIn(Enum):
        FROM_TODS = 1
        FROM_PC = 2
        FROM_0x5 = 3
    
    def signal_write(self, sel: SelMemAdrIn = SelMemAdrIn.FROM_TODS):
        if sel == self.SelMemAdrIn.FROM_TODS:
            addr = self.data_stack.tods()
            value = self.data_stack.next()
            self.memory.data[addr:addr + WORD_SIZE] = value.to_bytes(WORD_SIZE, byteorder="big", signed=True)

    def signal_read(self, sel: SelMemAdrIn, pc: int = None) -> int:
        if sel == self.SelMemAdrIn.FROM_PC:
            return int.from_bytes(
                self.memory.data[pc:pc + WORD_SIZE],
                byteorder="big",
                signed=True,
            )
        if sel == self.SelMemAdrIn.FROM_TODS:
            return int.from_bytes(
                self.memory.data[self.data_stack.tods():self.data_stack.tods() + WORD_SIZE],
                byteorder="big",
                signed=True,
            )
        if sel == self.SelMemAdrIn.FROM_0x5:
            return int.from_bytes(
                self.memory.data[INTR_VECTOR_ADDR:INTR_VECTOR_ADDR + WORD_SIZE],
                byteorder="big",
                signed=True,
            )
        
    class SelLeftAlu(Enum):
        FROM_NEXT = 1
        ZERO = 2

    def to_uint32(self, value: int) -> int:
        return value & 0xFFFFFFFF

    def to_int32(self, value: int) -> int:
        value &= 0xFFFFFFFF
        if value & 0x80000000:
            return value - 0x100000000
        return value

    def make_flags(self, result: int, overflow: bool = False, carry: bool = False) -> int:
        """
        Флаги в порядке NZVC:
        N = 8
        Z = 4
        V = 2
        C = 1
        """
        result32 = self.to_uint32(result)

        n = 1 if result32 & 0x80000000 else 0
        z = 1 if result32 == 0 else 0
        v = 1 if overflow else 0
        c = 1 if carry else 0

        return (n << 3) | (z << 2) | (v << 1) | c

    def alu(self, operation: str, sel_left: SelLeftAlu) -> tuple[int, int]:
        """
        Выполняет операцию ALU над значениями стека.

        Для бинарных операций:
        left  = NEXT
        right = TODS

        Для унарной inv:
        left  = 0
        right = TODS

        Возвращает:
        (result, flags)
        """
        right = self.data_stack.tods()

        if sel_left == self.SelLeftAlu.FROM_NEXT:
            left = self.data_stack.next()
        elif sel_left == self.SelLeftAlu.ZERO:
            left = 0
        else:
            raise ValueError(f"unknown ALU left selector: {sel_left}")

        left_u = self.to_uint32(left)
        right_u = self.to_uint32(right)

        left_s = self.to_int32(left)
        right_s = self.to_int32(right)

        overflow = False
        carry = False

        if operation == Opcode.ADD.value:
            raw = left_u + right_u
            result_u = raw & 0xFFFFFFFF
            result = self.to_int32(result_u)

            carry = raw > 0xFFFFFFFF
            overflow = ((left_s >= 0 and right_s >= 0 and result < 0) or
                        (left_s < 0 and right_s < 0 and result >= 0))

        elif operation == Opcode.SUB.value:
            raw = left_u - right_u
            result_u = raw & 0xFFFFFFFF
            result = self.to_int32(result_u)

            # C = borrow при вычитании
            carry = left_u < right_u
            overflow = ((left_s >= 0 and right_s < 0 and result < 0) or
                        (left_s < 0 and right_s >= 0 and result >= 0))

        elif operation == Opcode.MUL.value:
            raw = left_s * right_s
            result = self.to_int32(raw)

            overflow = raw < -(2 ** 31) or raw > 2 ** 31 - 1
            carry = raw < 0 or raw > 0xFFFFFFFF

        elif operation == Opcode.DIV.value:
            if right_s == 0:
                raise ZeroDivisionError("division by zero")

            raw = int(left_s / right_s)
            result = self.to_int32(raw)

            overflow = raw < -(2 ** 31) or raw > 2 ** 31 - 1
            carry = False

        elif operation == Opcode.AND.value:
            result = self.to_int32(left_u & right_u)

        elif operation == Opcode.OR.value:
            result = self.to_int32(left_u | right_u)

        elif operation == Opcode.XOR.value:
            result = self.to_int32(left_u ^ right_u)

        elif operation == Opcode.INV.value:
            result = self.to_int32(~right_u)

        else:
            raise ValueError(f"unknown ALU operation: {operation}")

        flags = self.make_flags(result, overflow=overflow, carry=carry)
        return result, flags


class ControlUnit:
    memory: Memory = None
    "Память."

    program_counter: int = None
    "Счётчик команд. Инициализируется нулём."

    instr_register: int = None
    "Регистр команд. Инициализируется нулём."

    ei_register: int = None
    "Регистр статуса прерываний. Инициализируется нулём, тк по дефолту прерывания запрещены."

    intr_req: bool = None
    "Есть ли запрос на прерывание. Инициализируется False. При true гарантируется, что в IN лежит значение."

    in_intr_flag: bool = None
    "Работаем ли мы сейчас в прерывании. Мнимый флаг. Инициализируется False."

    data_path: DataPath = None
    "Блок обработки данных."

    return_stack: ReturnStack = None

    _tick = None
    "Текущее модельное время процессора (в тактах). Инициализируется нулём."

    def __init__(self, program: Memory, data_path: DataPath):
        self.memory = program
        self.program_counter = 0
        self.instr_register = 0
        self.ei_register = 0
        self.intr_req = False
        self.in_intr_flag = False
        self.data_path = data_path
        self.return_stack = ReturnStack()
        self._tick = 0
        self.step = 0

    def tick(self):
        self._tick += 1

    def current_tick(self):
        return self._tick

    class SelPcIn(Enum):
        PLUS_1 = 1
        PLUS_4 = 2
        FROM_STACK = 3
        FROM_MEMORY = 4

    def signal_latch_program_counter(self, sel_next: SelPcIn, sel_mem: DataPath.SelMemAdrIn = None):
        if sel_next == self.SelPcIn.PLUS_1:
            self.program_counter += 1
        elif sel_next == self.SelPcIn.PLUS_4:
            self.program_counter += WORD_SIZE
        elif sel_next == self.SelPcIn.FROM_MEMORY:
            data = self.data_path.signal_read(sel_mem, self.program_counter)
            if data < 0:
                raise ValueError(f"negative jump address: {data}")
            if data >= len(self.memory.data):
                raise ValueError(f"jump address out of memory: {data}")
            self.program_counter = data
        elif sel_next == self.SelPcIn.FROM_STACK:
            self.program_counter = self.return_stack.pop()
            pass

    def signal_latch_instr_register(self):
        self.instr_register = self.memory.data[self.program_counter]

    def signal_latch_ei_register(self, enabled: bool):
        if enabled:
            self.ei_register = 1
        else:
            self.ei_register = 0

    def process_next_tick(self):
        """Основной цикл процессора. Декодирует и выполняет инструкцию."""

        # проверка буфера входных данных (IO CONTROLLER)
        if self.data_path.input_buffer and self.data_path.input_buffer[0][0] == self.current_tick():
            self.memory.data[IN_ADDR:IN_ADDR + WORD_SIZE] = self.data_path.input_buffer[0][1].to_bytes(WORD_SIZE, byteorder="big", signed=True)
            self.data_path.input_buffer.pop(0)
            self.intr_req = True

        # 1 tick -- instr fetch
        if self.step == 0:
            self.signal_latch_instr_register()
            self.signal_latch_program_counter(sel_next=self.SelPcIn.PLUS_1)
            self.step = 1
            self.tick()
            return
        
        bin_instr = self.instr_register
        opcode = decode_instr(bin_instr)

        # 2-3 tick -- instr exec [and parse operand]
        if opcode is Opcode.HALT:
            raise StopIteration()

        if opcode is Opcode.JUMP:
            if self.step == 1:
                self.signal_latch_program_counter(sel_next=self.SelPcIn.FROM_MEMORY, sel_mem=self.data_path.SelMemAdrIn.FROM_PC)
                self.step = 3
                self.tick()
                return

        if opcode is Opcode.JNZ:
            if self.step == 1:
                flag = self.data_path.data_stack.pop()

                if flag != 0:
                    self.signal_latch_program_counter(sel_next=self.SelPcIn.FROM_MEMORY, sel_mem=self.data_path.SelMemAdrIn.FROM_PC)
                else:
                    self.signal_latch_program_counter(sel_next=self.SelPcIn.PLUS_4)
                self.step = 3
                self.tick()
                return
        
        if opcode is Opcode.CALL:
            if self.step == 1:
                self.return_stack.push(self.program_counter)
                self.signal_latch_program_counter(sel_next=self.SelPcIn.FROM_MEMORY, sel_mem=self.data_path.SelMemAdrIn.FROM_PC)
                self.step = 3
                self.tick()
                return
        
        if opcode is Opcode.RET:
            # два такта, сначала загружаем из rs, затем увеличиваем pc на 4
            if self.step == 1:
                self.signal_latch_program_counter(sel_next=self.SelPcIn.FROM_STACK)
                self.step = 2
                self.tick()
                return
            if self.step == 2:
                self.signal_latch_program_counter(sel_next=self.SelPcIn.PLUS_4)
                self.step = 3
                self.tick()
                return

        if opcode is Opcode.IRET:
            # два такта, чтобы снять два значения со стека
            if self.step == 1:
                data = self.return_stack.pop()
                if data < 0 or data > 0xF:
                    raise ValueError(f"invalid NZVC value from return stack: {data}")
                self.data_path.signal_latch_nzvc(self.data_path.SelNzvcIn.FROM_RS, data)
                self.step = 2
                self.tick()
                return
            if self.step == 2:
                self.signal_latch_program_counter(sel_next=self.SelPcIn.FROM_STACK)
                self.signal_latch_ei_register(True)
                self.in_intr_flag = False
                self.step = 3
                self.tick()
                return

        if opcode in {Opcode.ADD, Opcode.SUB, Opcode.MUL, Opcode.DIV, Opcode.AND, Opcode.OR, Opcode.XOR}:
            if self.step == 1:
                res, flags = self.data_path.alu(opcode.value, self.data_path.SelLeftAlu.FROM_NEXT)
                self.data_path.data_stack.pop(res)
                self.data_path.signal_latch_nzvc(self.data_path.SelNzvcIn.FROM_ALU, flags)
                self.step = 3
                self.tick()
                return

        if opcode is Opcode.INV:
            if self.step == 1:
                res, flags = self.data_path.alu(opcode.value, self.data_path.SelLeftAlu.ZERO)
                self.data_path.data_stack.pop(res)
                self.data_path.signal_latch_nzvc(self.data_path.SelNzvcIn.FROM_ALU, flags)
                self.step = 3
                self.tick()
                return
            
        if opcode is Opcode.LOAD:
            if self.step == 1:
                data = self.data_path.signal_read(self.data_path.SelMemAdrIn.FROM_TODS)
                self.data_path.data_stack.latch_tods(data)
                self.step = 3
                self.tick()
                return

        if opcode is Opcode.STORE:
            # два такта, чтобы снять два значения со стека
            if self.step == 1:
                self.data_path.signal_write()
                addr = self.data_path.data_stack.pop()

                # проверка буфера выходных данных
                if addr == OUT_ADDR:
                    self.data_path.output_buffer.append(self.data_path.data_stack.tods())

                self.step = 2
                self.tick()
                return
            if self.step == 2:
                self.data_path.data_stack.pop()
                self.step = 3
                self.tick()
                return

        if opcode is Opcode.DI:
            if self.step == 1:
                self.signal_latch_ei_register(False)
                self.step = 3
                self.tick()
                return

        if opcode is Opcode.EI:
            if self.step == 1:
                self.signal_latch_ei_register(True)
                self.step = 3
                self.tick()
                return

        if opcode is Opcode.DROP:
            if self.step == 1:
                self.data_path.data_stack.pop()
                self.step = 3
                self.tick()
                return

        if opcode is Opcode.SWAP:
            if self.step == 1:
                self.data_path.data_stack.swap()
                self.step = 3
                self.tick()
                return

        if opcode is Opcode.OVER:
            if self.step == 1:
                self.data_path.data_stack.over()
                self.step = 3
                self.tick()
                return

        if opcode is Opcode.DUP:
            if self.step == 1:
                self.data_path.data_stack.dup()
                self.step = 3
                self.tick()
                return

        if opcode is Opcode.PUSH:
            if self.step == 1:
                data = self.data_path.signal_read(self.data_path.SelMemAdrIn.FROM_PC, self.program_counter)
                self.data_path.data_stack.push(data)
                self.signal_latch_program_counter(sel_next=self.SelPcIn.PLUS_4)
                self.step = 3
                self.tick()
                return
            

        if opcode is Opcode.PUSH_FLAGS:
            if self.step == 1:
                self.data_path.data_stack.push(self.data_path.nzvc_register)
                self.step = 3
                self.tick()
                return

        # intr fetch
        if self.step == 3:
            if self.ei_register == 1 and self.intr_req is True:
                # начинаем обработку прерывания
                self.return_stack.push(self.program_counter)
                self.signal_latch_program_counter(sel_next=self.SelPcIn.FROM_MEMORY, sel_mem=self.data_path.SelMemAdrIn.FROM_0x5)
                self.intr_req = False
                self.step = 4
                self.tick()
                return
            else:
                self.step = 0
                self.tick()
                return
        if self.step == 4:
            self.return_stack.push(self.data_path.nzvc_register)
            # выключаем прерывания
            self.signal_latch_ei_register(False)
            self.in_intr_flag = True
            self.step = 0
            self.tick()
            pass

    def __repr__(self):
        try:
            opcode = decode_instr(self.instr_register)
            instr = opcode.value

            if opcode in {Opcode.PUSH, Opcode.JUMP, Opcode.JNZ, Opcode.CALL}:
                if self.step == 1:
                    arg = self.data_path.signal_read(
                        self.data_path.SelMemAdrIn.FROM_PC,
                        self.program_counter,
                    )
                else:
                    arg = ''
                instr = f"{instr} {arg}"

        except Exception:
            instr = f"unknown(0x{self.instr_register:02X})"

        return (
            f"TICK: {self._tick:04} | "
            f"PC: {self.program_counter:04} | "
            f"STEP: {(self.step - 1) % 4} | "
            f"IR: 0x{self.instr_register:02X} ({instr}) | "
            f"NZVC: {self.data_path.nzvc_register:04b} | "
            f"EI: {self.ei_register} | "
            f"INTR: {int(self.intr_req)} | "
            f"IN INTR: {int(self.in_intr_flag)} | "
            f"DS: {self.data_path.data_stack.data_stack_memory} | "
            f"RS: {self.return_stack.data_stack_memory} | "
            f"OUT: {self.data_path.output_buffer}"
        )


def simulation(program: bytes, input_tokens: list[tuple[int, int]], limit: int):
    memory = Memory(program)
    data_path = DataPath(memory, input_tokens)
    control_unit = ControlUnit(memory, data_path)

    logging.debug("%s", control_unit)
    try:
        while control_unit._tick < limit:
            control_unit.process_next_tick()
            logging.debug("%s", control_unit)
    except EOFError:
        logging.warning("Input buffer is empty!")
    except StopIteration:
        pass

    if control_unit._tick >= limit:
        logging.warning("Limit exceeded!")
    output = "".join(chr(value) for value in data_path.output_buffer)
    logging.info("output_buffer: %s", repr(output))
    return output, control_unit.current_tick()


def parse_input(text: str) -> list[tuple[int, int]]:
    pattern = re.compile(
        r"\(\s*(\d+)\s*,\s*(?:'((?:\\.|[^']))'|(-?\d+))\s*\)"
    )

    input_token = []

    for match in pattern.finditer(text):
        tick_str, char_str, num_str = match.groups()

        tick = int(tick_str)

        if char_str is not None:
            value = bytes(char_str, "utf-8").decode("unicode_escape")

            if len(value) != 1:
                raise ValueError(f"Invalid char: {value!r}")

            value = ord(value)

            if not 0 <= value <= 127:
                raise ValueError(f"Char must be ASCII: {value!r}")

        else:
            value = int(num_str)

            if not -(2**31) <= value <= 2**31 - 1:
                raise ValueError(f"Number does not fit into int32: {value}")

        input_token.append((tick, value))
    
    return input_token


def main(code_file, input_file, limit=4000):
    with open(code_file, "rb") as file:
        binary_code = file.read()

    with open(input_file, encoding="utf-8") as file:
        input_text = file.read()

    output, ticks = simulation(
        binary_code,
        input_tokens=parse_input(input_text),
        limit=limit,
    )

    print("".join(output))
    print("ticks:", ticks)


if __name__ == "__main__":
    logging.getLogger().setLevel(logging.DEBUG)

    parser = argparse.ArgumentParser()
    parser.add_argument("code_file")
    parser.add_argument("input_file")
    parser.add_argument("--limit", type=int, default=4000)

    args = parser.parse_args()

    main(args.code_file, args.input_file, args.limit)