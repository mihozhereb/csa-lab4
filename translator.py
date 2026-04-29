import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

from isa import Instruction, Opcode, Term, instr_size, to_bytes, to_hex


WORD_SIZE = 4
INIT_SIZE = 17
INTERRUPT_HANDLER_NAME = "interruption_handler"


BUILTINS = {
    "+": Opcode.ADD,
    "-": Opcode.SUB,
    "*": Opcode.MUL,
    "/": Opcode.DIV,
    "&": Opcode.AND,
    "|": Opcode.OR,
    "^": Opcode.XOR,
    "~": Opcode.INV,

    "dup": Opcode.DUP,
    "drop": Opcode.DROP,
    "swap": Opcode.SWAP,
    "over": Opcode.OVER,

    "@": Opcode.LOAD,
    "!": Opcode.STORE,

    "push_flags": Opcode.PUSH_FLAGS,

    "di": Opcode.DI,
    "ei": Opcode.EI,
    "iret": Opcode.IRET
}


class TranslationError(Exception):
    pass


@dataclass
class Variable:
    name: str
    address: int
    data: bytes
    term: Term


@dataclass
class WordDef:
    name: str
    terms: list[Term]
    term: Term
    address: int = 0
    code: list[Instruction] = field(default_factory=list)


@dataclass
class Program:
    variables: dict[str, Variable]
    words: dict[str, WordDef]
    main_terms: list[Term]
    data_image: bytes = b""
    code_start: int = 0
    main_address: int = 0
    main_code: list[Instruction] = field(default_factory=list)


def fail(term: Term | None, message: str) -> None:
    if term is None:
        raise TranslationError(message)
    raise TranslationError(f"{term.line}:{term.pos}: {message}: {term.word!r}")


def tokenize(text: str) -> list[Term]:
    """
    Разбивает исходный текст на термы.

    Удаляет комментарии:
    - \\ комментарий
    - ( комментарий )
    """
    terms: list[Term] = []

    TOKEN_RE = re.compile(r's"[^"]*"|\S+')

    for line_num, line in enumerate(text.splitlines(), 1):
        line = line.split("\\", 1)[0]

        line = re.sub(r"\([^)]*\)", " ", line)

        for match in TOKEN_RE.finditer(line):
            word = match.group(0)
            pos = match.start() + 1
            terms.append(Term(line_num, pos, word))

    return terms


def string_value(token: str) -> str:
    if not token.startswith('s"') or not token.endswith('"'):
        raise ValueError("not string")
    return token[2:-1]


def load_with_includes(path: Path, seen: set[Path] | None = None) -> list[Term]:
    """
    Загружает файл и inline-подставляет INCLUDE.
    """
    if seen is None:
        seen = set()

    path = path.resolve()

    if path in seen:
        raise TranslationError(f"cyclic include: {path}")

    seen.add(path)

    text = path.read_text(encoding="utf-8")
    terms = tokenize(text)

    result: list[Term] = []

    i = 0
    while i < len(terms):
        term = terms[i]

        if term.word == "INCLUDE":
            if i + 1 >= len(terms):
                fail(term, "expected string after INCLUDE")

            file_term = terms[i + 1]

            try:
                include_name = string_value(file_term.word)
            except ValueError:
                fail(file_term, "INCLUDE expects string literal")

            include_path = path.parent / include_name

            if not include_path.exists():
                fail(file_term, f"include file not found: {include_path}")

            result.extend(load_with_includes(include_path, seen))
            i += 2
            continue

        result.append(term)
        i += 1

    seen.remove(path)
    return result


def is_number(word: str) -> bool:
    try:
        int(word, 10)
        return True
    except ValueError:
        return False


def encode_word(value: int) -> bytes:
    return value.to_bytes(WORD_SIZE, byteorder="big", signed=True)


def encode_string(value: str) -> bytes:
    """
    Строка хранится как последовательность машинных слов:
    один символ = одно машинное слово.
    В конце добавляется нулевое машинное слово.
    """
    data = bytearray()

    for ch in value:
        data.extend(ord(ch).to_bytes(WORD_SIZE, byteorder="big", signed=True))

    data.extend((0).to_bytes(WORD_SIZE, byteorder="big", signed=True))
    return bytes(data)


def parse_program(terms: list[Term], data_start: int = 0) -> Program:
    """
    Первый проход:
    - собирает переменные;
    - собирает определения слов;
    - отделяет main-код;
    - проверяет грубую структуру определений.
    """
    variables: dict[str, Variable] = {}
    words: dict[str, WordDef] = {}
    main_terms: list[Term] = []

    data_addr = data_start
    data_image = bytearray()

    i = 0

    while i < len(terms):
        term = terms[i]

        if term.word == "VAR":
            if i + 2 >= len(terms):
                fail(term, "bad VAR declaration")

            value_term = terms[i + 1]

            if value_term.word == "ALLOC":
                if i + 3 >= len(terms):
                    fail(term, "bad VAR ALLOC declaration")

                size_term = terms[i + 2]
                name_term = terms[i + 3]

                if not is_number(size_term.word):
                    fail(size_term, "ALLOC size must be number")

                size = int(size_term.word, 10)

                if size < 0:
                    fail(size_term, "ALLOC size must be non-negative")

                data = bytes(size * WORD_SIZE)
                i += 4

            else:
                name_term = terms[i + 2]

                if is_number(value_term.word):
                    data = encode_word(int(value_term.word, 10))
                elif value_term.word.startswith('s"'):
                    data = encode_string(string_value(value_term.word))
                else:
                    fail(value_term, "VAR expects number, string or ALLOC")

                i += 3

            variables[name_term.word] = Variable(
                name=name_term.word,
                address=data_addr,
                data=data,
                term=name_term,
            )

            data_addr += len(data)
            data_image.extend(data)
            continue

        if term.word == ":":
            if i + 2 >= len(terms):
                fail(term, "bad word definition")

            name_term = terms[i + 1]

            body: list[Term] = []

            i += 2

            while i < len(terms):
                if terms[i].word == ";":
                    break

                body.append(terms[i])
                i += 1

            if i >= len(terms):
                fail(term, "word definition without ';'")

            words[name_term.word] = WordDef(
                name=name_term.word,
                terms=body,
                term=name_term,
            )

            i += 1
            continue

        main_terms.append(term)
        i += 1

    return Program(
        variables=variables,
        words=words,
        main_terms=main_terms,
        data_image=bytes(data_image),
    )


def compile_terms(
    terms: list[Term],
    variables: dict[str, Variable],
    words: dict[str, WordDef],
    start_addr: int,
) -> list[Instruction]:
    """
    Второй проход:
    - генерирует инструкции;
    - патчит адреса IF/ELSE/THEN;
    - патчит адреса BEGIN/WHILE/REPEAT;
    - проверяет обращения к неизвестным именам.
    """
    code: list[Instruction] = []

    def current_addr() -> int:
        return start_addr + sum(instr_size(instr) for instr in code)

    def emit(opcode: Opcode, term: Term, arg: int | None = None) -> int:
        code.append(Instruction(opcode=opcode, term=term, arg=arg))
        return len(code) - 1

    def patch(index: int, arg: int) -> None:
        code[index].arg = arg

    def compile_range(pos: int, stop_words: set[str]) -> tuple[int, str | None]:
        while pos < len(terms):
            term = terms[pos]
            word = term.word

            if word in stop_words:
                return pos, word

            if is_number(word):
                emit(Opcode.PUSH, term, int(word, 10))

            elif word in BUILTINS:
                emit(BUILTINS[word], term)

            elif word in variables:
                emit(Opcode.PUSH, term, variables[word].address)

            elif word in words:
                emit(Opcode.CALL, term, words[word].address)

            elif word == "IF":
                pos = compile_if(pos + 1, term)
                continue

            elif word == "BEGIN":
                pos = compile_loop(pos + 1, term)
                continue

            elif word in {"ELSE", "THEN", "WHILE", "REPEAT", ";"}:
                fail(term, f"unexpected {word}")

            else:
                fail(term, "unknown variable or word")

            pos += 1

        return pos, None

    def compile_if(pos: int, if_term: Term) -> int:
        jnz_true_index = emit(Opcode.JNZ, if_term, 0)
        jump_false_index = emit(Opcode.JUMP, if_term, 0)

        true_addr = current_addr()
        patch(jnz_true_index, true_addr)

        pos, stop = compile_range(pos, {"ELSE", "THEN"})

        if stop is None:
            fail(if_term, "IF without THEN")

        if stop == "ELSE":
            else_term = terms[pos]

            jump_end_index = emit(Opcode.JUMP, else_term, 0)

            false_addr = current_addr()
            patch(jump_false_index, false_addr)

            pos, stop = compile_range(pos + 1, {"THEN"})

            if stop != "THEN":
                fail(if_term, "IF ELSE without THEN")

            end_addr = current_addr()
            patch(jump_end_index, end_addr)

            return pos + 1

        end_addr = current_addr()
        patch(jump_false_index, end_addr)

        return pos + 1

    def compile_loop(pos: int, begin_term: Term) -> int:
        begin_addr = current_addr()

        pos, stop = compile_range(pos, {"WHILE"})

        if stop != "WHILE":
            fail(begin_term, "BEGIN without WHILE")

        while_term = terms[pos]

        jnz_body_index = emit(Opcode.JNZ, while_term, 0)
        jump_end_index = emit(Opcode.JUMP, while_term, 0)

        body_addr = current_addr()
        patch(jnz_body_index, body_addr)

        pos, stop = compile_range(pos + 1, {"REPEAT"})

        if stop != "REPEAT":
            fail(begin_term, "BEGIN WHILE without REPEAT")

        repeat_term = terms[pos]

        emit(Opcode.JUMP, repeat_term, begin_addr)

        end_addr = current_addr()
        patch(jump_end_index, end_addr)

        return pos + 1

    pos, stop = compile_range(0, set())

    if stop is not None or pos != len(terms):
        fail(terms[pos], "unexpected token")

    return code


def assign_addresses(program: Program, data_start: int) -> None:
    program.code_start = data_start + len(program.data_image)

    current = program.code_start

    available_words = {}

    for word in program.words.values():
        word.address = current

        word.code = compile_terms(
            word.terms,
            program.variables,
            available_words,
            current,
        )

        word.code.append(Instruction(Opcode.RET, word.term))

        current += sum(instr_size(instr) for instr in word.code)

        available_words[word.name] = word

    program.main_address = current

    program.main_code = compile_terms(
        program.main_terms,
        program.variables,
        program.words,
        program.main_address,
    )

    halt_term = Term(0, 0, "halt")
    program.main_code.append(Instruction(Opcode.HALT, halt_term))


def program_code(program: Program) -> list[Instruction]:
    code: list[Instruction] = []

    for word in program.words.values():
        code.extend(word.code)

    code.extend(program.main_code)
    return code


def init_data(program: Program) -> bytes:
    """
    Первые 17 байт памяти:
    - 0..4   : jump main_address
    - 5..8   : адрес interruption_handler или 0
    - 9..16  : зарезервировано под I/O
    """

    handler = program.words.get(INTERRUPT_HANDLER_NAME)
    handler_addr = handler.address if handler is not None else 0

    result = bytearray()

    result.extend(to_bytes([
        Instruction(Opcode.JUMP, Term(0, 0, "init"), program.main_address)
    ]))

    result.extend(handler_addr.to_bytes(4, byteorder="big", signed=True))

    result.extend(bytes(INIT_SIZE - len(result)))

    return bytes(result)


def program_to_bytes(program: Program) -> bytes:
    """
    Формирует бинарный образ памяти:
    сначала INIT_DATA, потом данные, потом функции, потом main-код.
    """
    return init_data(program) + program.data_image + to_bytes(program_code(program))


def bytes_hex(data: bytes) -> str:
    return data.hex(" ").upper()


def program_to_hex(program: Program) -> str:
    """
    Выводит весь образ памяти
    """
    result: list[str] = []

    init = init_data(program)

    result.append(
        f"0 - 00000000 - {bytes_hex(init[:5])} - init: jump {program.main_address}"
    )

    handler = program.words.get(INTERRUPT_HANDLER_NAME)
    handler_addr = handler.address if handler is not None else 0

    result.append(
        f"5 - 00000005 - {bytes_hex(init[5:9])} - init: interrupt vector {handler_addr}"
    )

    result.append(
        f"9 - 00000009 - {bytes_hex(init[9:13])} - init: io in reserved"
    )

    result.append(
        f"13 - 0000000D - {bytes_hex(init[13:17])} - init: io out reserved"
    )

    for variable in program.variables.values():
        result.append(
            f"{variable.address} - {variable.address:08X} - {bytes_hex(variable.data)} - var: {variable.name}"
        )

    code = program_code(program)
    code_hex = to_hex(code, base_addr=program.code_start)

    if code_hex:
        result.append(code_hex)

    return "\n".join(result)


def translate(source_path: str, data_start: int = 0) -> Program:
    terms = load_with_includes(Path(source_path))
    program = parse_program(terms, data_start=data_start)
    assign_addresses(program, data_start=data_start)
    return program


def main(source: str, target: str) -> None:
    program = translate(source, data_start=INIT_SIZE)

    code = program_code(program)
    binary_code = program_to_bytes(program)
    hex_code = program_to_hex(program)

    os.makedirs(os.path.dirname(os.path.abspath(target)) or ".", exist_ok=True)

    with open(target, "wb") as f:
        f.write(binary_code)

    with open(target + ".hex", "w", encoding="utf-8") as f:
        f.write(hex_code)

    print("code instr:", len(code))
    print("data bytes:", len(program.data_image))
    print("total bytes:", len(binary_code))


if __name__ == "__main__":
    assert len(sys.argv) == 3, "Usage: translator.py <input.fs> <target.bin>"
    _, source, target = sys.argv
    main(source, target)
