from enum import Enum
import logging
import sys

from isa import Instruction, Opcode, decode_instr, from_bytes, has_arg, opcode_to_binary


class DataPath:
    memory = None
    "Память. Инициализируется входными данными конструктора."

    stack = None
    "Стек данных."

    nzvc_register = None
    "Регистр флагов nzvc. Инициализируется нулём."

    input_buffer = None
    "Буфер входных данных. Инициализируется входными данными конструктора."

    output_buffer = None
    "Буфер выходных данных."

    def __init__(self, data_memory_size, input_buffer):
        self.memory = 
        self.nzvc_register = 0
        self.input_buffer = input_buffer
        self.output_buffer = []

    def signal_latch_data_addr(self, sel):
        assert sel in {Opcode.LEFT.value, Opcode.RIGHT.value}, "internal error, incorrect selector: {}".format(sel)

        if sel == Opcode.LEFT.value:
            self.data_address -= 1
        elif sel == Opcode.RIGHT.value:
            self.data_address += 1

        assert 0 <= self.data_address < self.data_memory_size, "out of memory: {}".format(self.data_address)

    def signal_latch_acc(self):
        self.acc = self.data_memory[self.data_address]

    def signal_wr(self, sel):
        assert sel in {
            Opcode.INC.value,
            Opcode.DEC.value,
            Opcode.INPUT.value,
        }, "internal error, incorrect selector: {}".format(sel)

        if sel == Opcode.INC.value:
            self.data_memory[self.data_address] = self.acc + 1
            if self.data_memory[self.data_address] == 128:
                self.data_memory[self.data_address] = -128
        elif sel == Opcode.DEC.value:
            self.data_memory[self.data_address] = self.acc - 1
            if self.data_memory[self.data_address] == -129:
                self.data_memory[self.data_address] = 127
        elif sel == Opcode.INPUT.value:
            if len(self.input_buffer) == 0:
                raise EOFError()
            symbol = self.input_buffer.pop(0)
            symbol_code = ord(symbol)
            assert -128 <= symbol_code <= 127, "input token is out of bound: {}".format(symbol_code)
            self.data_memory[self.data_address] = symbol_code
            logging.debug("input: %s", repr(symbol))

    def zero(self):
        return self.acc == 0


class ControlUnit:
    memory: bytes = None
    "Память."

    program_counter = None
    "Счётчик команд. Инициализируется нулём."

    instr_register = None
    "Регистр команд. Инициализируется нулём."

    data_path = None
    "Блок обработки данных."

    _tick = None
    "Текущее модельное время процессора (в тактах). Инициализируется нулём."

    def __init__(self, program, data_path):
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

    def signal_latch_program_counter(self, sel_next):
        if sel_next:
            self.program_counter += 1
        else:
            instr = self.program[self.program_counter]
            assert "arg" in instr, "internal error"
            self.program_counter = instr["arg"]

    class SelPcIn(Enum):
        PLUS_1 = 1
        PLUS_4 = 2
        FROM_STACK = 3
        FROM_MEMORY = 4

    def signal_latch_instr_register(self, sel: SelPcIn):
        self.instr_register = self.memory[self.program_counter]

    def process_next_tick(self):
        """Основной цикл процессора. Декодирует и выполняет инструкцию."""

        # 1 tick -- instr fetch
        self.signal_latch_instr_register()

        bin_instr = self.instr_register
        opcode = decode_instr(bin_instr)

        self.signal_latch_program_counter(sel_next=True)

        # 2-...n-1 tick -- instr exec [and parse operand]

        if opcode is Opcode.HALT:
            raise StopIteration()

        if opcode is Opcode.JMP:
            addr = int.from_bytes(
                self.memory[self.program_counter + 1:self.program_counter + 5],
                byteorder="big",
                signed=True,
            )
            self.program_counter = addr
            self.step = 0
            self.tick()
            return

        if opcode is Opcode.JZ:
            if self.step == 0:
                addr = instr["arg"]
                self.data_path.signal_latch_acc()
                self.step = 1
                self.tick()
                return
            if self.step == 1:
                if self.data_path.zero():
                    self.signal_latch_program_counter(sel_next=False)
                else:
                    self.signal_latch_program_counter(sel_next=True)
                self.step = 0
                self.tick()
                return

        if opcode in {Opcode.RIGHT, Opcode.LEFT}:
            self.data_path.signal_latch_data_addr(opcode.value)
            self.signal_latch_program_counter(sel_next=True)
            self.step = 0
            self.tick()
            return

        if opcode in {Opcode.INC, Opcode.DEC, Opcode.INPUT}:
            if self.step == 0:
                self.data_path.signal_latch_acc()
                self.step = 1
                self.tick()
                return
            if self.step == 1:
                self.data_path.signal_wr(opcode.value)
                self.signal_latch_program_counter(sel_next=True)
                self.step = 0
                self.tick()
                return

        if opcode is Opcode.PRINT:
            if self.step == 0:
                self.data_path.signal_latch_acc()
                self.step = 1
                self.tick()
                return
            if self.step == 1:
                self.data_path.signal_output()
                self.signal_latch_program_counter(sel_next=True)
                self.step = 0
                self.tick()
                return
        
        # intr fetch

    def __repr__(self):
        """Вернуть строковое представление состояния процессора."""
        state_repr = "TICK: {:3} PC: {:3}/{} ADDR: {:3} MEM_OUT: {} ACC: {}".format(
            self._tick,
            self.program_counter,
            self.step,
            self.data_path.data_address,
            self.data_path.data_memory[self.data_path.data_address],
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