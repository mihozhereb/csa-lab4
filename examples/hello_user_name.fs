INCLUDE s"libs/io.fs"

VAR s"What is your name?" PROMPT
VAR s"Hello, " HELLO
VAR s"!" EXCL
VAR ALLOC 32 NAME

: PRINT
    BEGIN
        dup @
    WHILE
        dup @ WRITE_CHAR
        4 +
    REPEAT
    drop
;

: READ_NAME
    BEGIN
        READ_CHAR
        dup
    WHILE
        over !
        4 +
    REPEAT

    drop
    0 swap !
;

PROMPT PRINT
10 WRITE_CHAR

ei
NAME READ_NAME
di

HELLO PRINT
NAME PRINT
EXCL PRINT
10 WRITE_CHAR