from enum import Enum
import logging
import sys

from isa import Opcode, decode_instr, opcode_to_binary


class Memory:
    data: bytes = None

    def __init__(self, memory: bytes):
        self.data = memory

    # def read(self, data_address: int) -> int:
    #     return self.data[data_address]

    # def write(self, data_address: int, value: int):
    #     self.data[data_address] = value


class DataStack:
    data_stack_memory: list[int] = None

    def tods(self) -> int:
        return self.data_stack_memory[-1]

    def next(self) -> int:
        return self.data_stack_memory[-2]

    def pop(self, value_from_alu: int = None) -> int:
        res = self.data_stack_memory.pop()
        if value_from_alu:
            self.data_stack_memory[-1] = value_from_alu
        return res

    def push(self, number: int):
        self.data_stack_memory.append(number)

    def swap(self):
        self.data_stack_memory[0], self.data_stack_memory[1] = self.data_stack_memory[1], self.data_stack_memory[0]

    def over(self):
        self.data_stack_memory.append(self.data_stack_memory[-2])
    
    def dup(self):
        self.data_stack_memory.append(self.data_stack_memory[-1])


class ReturnStack:
    data_stack_memory: list[int] = None

    def tors(self) -> int:
        return self.data_stack_memory[-1]
    
    def pop(self) -> int:
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
        self.nzvc_register = 0
        self.input_buffer = input_buffer
        self.output_buffer = []

    # def signal_latch_data_addr(self, sel):
    #     assert sel in {Opcode.LEFT.value, Opcode.RIGHT.value}, "internal error, incorrect selector: {}".format(sel)

    #     if sel == Opcode.LEFT.value:
    #         self.data_address -= 1
    #     elif sel == Opcode.RIGHT.value:
    #         self.data_address += 1

    #     assert 0 <= self.data_address < self.data_memory_size, "out of memory: {}".format(self.data_address)

    def signal_latch_nzvc(self, flags: int):
        self.nzvc_register = flags

    # def signal_wr(self, sel):
    #     assert sel in {
    #         Opcode.INC.value,
    #         Opcode.DEC.value,
    #         Opcode.INPUT.value,
    #     }, "internal error, incorrect selector: {}".format(sel)

    #     if sel == Opcode.INC.value:
    #         self.data_memory[self.data_address] = self.acc + 1
    #         if self.data_memory[self.data_address] == 128:
    #             self.data_memory[self.data_address] = -128
    #     elif sel == Opcode.DEC.value:
    #         self.data_memory[self.data_address] = self.acc - 1
    #         if self.data_memory[self.data_address] == -129:
    #             self.data_memory[self.data_address] = 127
    #     elif sel == Opcode.INPUT.value:
    #         if len(self.input_buffer) == 0:
    #             raise EOFError()
    #         symbol = self.input_buffer.pop(0)
    #         symbol_code = ord(symbol)
    #         assert -128 <= symbol_code <= 127, "input token is out of bound: {}".format(symbol_code)
    #         self.data_memory[self.data_address] = symbol_code
    #         logging.debug("input: %s", repr(symbol))

    # def zero(self):
    #     return self.acc == 0


class ControlUnit:
    memory: Memory = None
    "Память."

    program_counter: int = None
    "Счётчик команд. Инициализируется нулём."

    instr_register: int = None
    "Регистр команд. Инициализируется нулём."

    data_path: DataPath = None
    "Блок обработки данных."

    return_stack: ReturnStack = None

    _tick = None
    "Текущее модельное время процессора (в тактах). Инициализируется нулём."

    def __init__(self, program: Memory, data_path: DataPath):
        self.memory = program
        self.program_counter = 0
        self.instr_register = 0
        self.data_path = data_path
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

    def signal_latch_program_counter(self, sel_next: SelPcIn):
        if sel_next == self.SelPcIn.PLUS_1:
            self.program_counter += 1
        elif sel_next == self.SelPcIn.PLUS_4:
            self.program_counter += 4
        elif sel_next == self.SelPcIn.FROM_MEMORY:
            addr = int.from_bytes(
                self.memory.data[self.program_counter:self.program_counter + 4],
                byteorder="big",
                signed=False,
            )
            self.program_counter = addr
        elif sel_next == self.SelPcIn.FROM_STACK:
            self.program_counter = self.return_stack.pop()
            pass

    def signal_latch_instr_register(self):
        self.instr_register = self.memory.data[self.program_counter]

    def process_next_tick(self):
        """Основной цикл процессора. Декодирует и выполняет инструкцию."""

        # 1 tick -- instr fetch
        if self.step == 0:
            self.signal_latch_instr_register()

            bin_instr = self.instr_register
            opcode = decode_instr(bin_instr)

            self.signal_latch_program_counter(sel_next=self.SelPcIn.PLUS_1)
            self.step = 1
            self.tick()
            return

        # 2-...n-1 tick -- instr exec [and parse operand]

        if opcode is Opcode.HALT:
            raise StopIteration()

        if opcode is Opcode.JUMP:
            if self.step == 1:
                self.signal_latch_program_counter(self.SelPcIn.FROM_MEMORY)
                self.step = 0
                self.tick()
                return

        if opcode is Opcode.JNZ:
            if self.step == 1:
                if self.data_path.stack.tods == 0:
                    self.signal_latch_program_counter(sel_next=self.SelPcIn.FROM_MEMORY)
                else:
                    self.signal_latch_program_counter(sel_next=self.SelPcIn.PLUS_4)
                self.step = 0
                self.tick()
                return
        
        if opcode is Opcode.CALL:
            if self.step == 1:
                self.return_stack.push(self.program_counter)
                self.signal_latch_program_counter(self.SelPcIn.FROM_MEMORY)
                self.step = 0
                self.tick()
                return
        
        if opcode is Opcode.RET:
            if self.step == 1:
                self.signal_latch_program_counter(self.SelPcIn.FROM_STACK)
                self.step = 0
                self.tick()
                return

        if opcode is Opcode.IRET:
            if self.step == 1:
                # save flags in return stack 
                pass

        if opcode in {Opcode.ADD, Opcode.SUB, Opcode.MUL, Opcode.DIV, Opcode.AND, Opcode.OR, Opcode.XOR}:
            if self.step == 1:
                res, flags = self.data_path.alu(opcode.value, self.data_path.alu.SelLeftAlu.FROM_NEXT)
                self.data_path.data_stack.pop(res)
                self.data_path.signal_latch_nzvc(flags)
                self.signal_latch_program_counter(sel_next=self.SelPcIn.PLUS_1)
                self.step = 0
                self.tick()
                return

        if opcode is Opcode.INV:
            if self.step == 1:
                res, flags = self.data_path.alu(opcode.value, self.data_path.alu.SelLeftAlu.ZERO)
                self.data_path.data_stack.pop(res)
                self.data_path.signal_latch_nzvc(flags)
                self.signal_latch_program_counter(sel_next=self.SelPcIn.PLUS_1)
                self.step = 0
                self.tick()
                return
            
        if opcode is 

        # intr fetch

    def __repr__(self):
        """Вернуть строковое представление состояния процессора."""
        state_repr = "TICK: {:3} PC: {:3}/{} ADDR: {:3} MEM_OUT: {} ACC: {}".format(
            self._tick,
            self.program_counter,
            self.step,
            self.data_path.data_address,
            self.data_path.data_memory.data[self.data_path.data_address],
            self.data_path.acc,
        )

        instr = self.program[self.program_counter]
        opcode = instr["opcode"]
        instr_repr = str(opcode)

        if "arg" in instr:
            instr_repr += " {}".format(instr["arg"])

        instr_hex = f"{opcode_to_binary[opcode] << 28 | (instr.get('arg', 0) & 0x0FFFFFFF):08X}"

        return "{} \t{} [{}]".format(state_repr, instr_repr, instr_hex)


def simulation(program: bytes, input_tokens: list[tuple], data_memory_size: int, limit: int):
    data_path = DataPath(data_memory_size, input_tokens)
    control_unit = ControlUnit(program, data_path)

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
    logging.info("output_buffer: %s", repr("".join(data_path.output_buffer)))
    return "".join(data_path.output_buffer), control_unit.current_tick()


def main(code_file, input_file):
    with open(code_file, "rb") as file:
        binary_code = file.read()

    with open(input_file, encoding="utf-8") as file:
        input_text = file.read()
        input_token = []
        for char in input_text:
            input_token.append(char)

    output, ticks = simulation(
        binary_code,
        input_tokens=input_token,
        data_memory_size=100,
        limit=2000,
    )

    print("".join(output))
    print("ticks:", ticks)


if __name__ == "__main__":
    logging.getLogger().setLevel(logging.DEBUG)
    assert len(sys.argv) == 3, "Wrong arguments: machine.py <code_file> <input_file>"
    _, code_file, input_file = sys.argv
    main(code_file, input_file)