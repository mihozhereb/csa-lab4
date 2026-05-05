import contextlib
import io
import logging
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

import machine
import translator

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))


MAX_LOG = 700


@pytest.mark.golden_test("golden/*.yml")
def test_translator_and_machine(golden, caplog):
    # Установим уровень отладочного вывода на DEBUG
    caplog.set_level(logging.DEBUG)

    # Создаём временную папку для тестирования приложения.
    with tempfile.TemporaryDirectory() as tmpdirname:
        # Готовим имена файлов для входных и выходных данных.
        tmpdir = Path(tmpdirname)

        source = tmpdir / "source.fs"
        input_stream = tmpdir / "input.txt"
        target = tmpdir / "target.bin"
        target_hex = tmpdir / "target.bin.hex"

        # Записываем входные данные в файлы. Данные берутся из теста.
        with open(source, "w", encoding="utf-8") as file:
            file.write(golden["in_source"])
        with open(input_stream, "w", encoding="utf-8") as file:
            file.write(golden["in_stdin"])

        # Копируем библиотеки
        libs_dir = tmpdir / "libs"
        libs_dir.mkdir()
        for lib_name in ("io.fs", "math.fs"):
            lib_path = PROJECT_ROOT / "examples/libs" / lib_name

            if lib_path.exists():
                shutil.copy(lib_path, libs_dir / lib_name)

        # Запускаем транслятор и собираем весь стандартный вывод в переменную
        # stdout
        with contextlib.redirect_stdout(io.StringIO()) as stdout:
            translator.main(str(source), str(target))
            print("============================================================")
            machine.main(str(target), str(input_stream), limit=golden.get("in_limit") or 4000)

        # Выходные данные также считываем в переменные.
        code = target.read_bytes().hex(" ").upper()
        code_hex = target_hex.read_text(encoding="utf-8")

        # Проверяем, что ожидания соответствуют реальности.
        assert code == golden.out["out_code"]
        assert code_hex == golden.out["out_code_hex"]
        assert stdout.getvalue() == golden.out["out_stdout"]
        assert "\n".join(caplog.text.split("\n")[0:MAX_LOG]) + "EOF" == golden.out["out_log"]
