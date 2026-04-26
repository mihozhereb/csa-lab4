# Лабораторная работа №4

- Жеребцов Михаил Александрович, группа P3217, ису 465887
- `forth | stack | neum | hw | tick | binary | trap | mem | cstr | prob2 | cache`

## Язык программирования - Forth

### Описание синтаксиса

``` ebnf
<program> ::= <terms>

<terms> ::= { <term> }

<term> ::= <number>
         | <operand>
         | <identifier>
         | <var_init>
         | <word_init>
         | <if-term>
         | <loop-term>
         | <import-term>
         | <comment>

<number> ::= <знаковое десятичное число>
<string> ::= s"<любая последовательность символов>"

<operand> ::= "+"
            | "-"
            | "/"
            | "*"
            | "&"
            | "|"
            | "^"
            | "~"
            | "dup"
            | "drop"
            | "swap"
            | "over"
            | "@"
            | "!"

<identifier> ::= <letter> { <letter> | <digit> | "_" }

<var_name> ::= <identifier>
<var_init> ::= "VAR" <number> <var_name>
             | "VAR" <string> <var_name>
             | "VAR" "" <number> <var_name>

<word> ::= <identifier>
<word_init> ::= ":" <word> <terms> ";"

<if-term> ::= "IF" <terms> "THEN"
            | "IF" <terms> "ELSE" <terms> "THEN"

<loop-term> ::= "BEGIN" <terms> "WHILE" <terms> "REPEAT"

<import-term> ::= "INCLUDE" <string>

<comment> ::= "\" <любая последовательность символов до переноса строки>
            | "(" <любая последовательность символов> ")"
```
