INCLUDE s"libs/io.fs"

VAR ALLOC 16 ARR
VAR 0 LEN
VAR 0 I
VAR 0 J

: ARR_ADDR
    4 * ARR +
;

: ARR_GET
    ARR_ADDR @
;

: ARR_SET
    ARR_ADDR !
;

: READ_LIST
    0 LEN !

    BEGIN
        READ_CHAR dup
    WHILE
        LEN @ ARR_SET
        LEN @ 1 + LEN !
    REPEAT

    drop
;

: SORT
    0 I !

    BEGIN
        I @ LEN @ 1 - <
    WHILE
        0 J !

        BEGIN
            J @ LEN @ I @ - 1 - <
        WHILE
            J @ ARR_GET
            J @ 1 + ARR_GET

            2dup >
            IF
                J @ ARR_SET
                J @ 1 + ARR_SET
            ELSE
                2drop
            THEN

            J @ 1 + J !
        REPEAT

        I @ 1 + I !
    REPEAT
;

: PRINT_LIST
    0 I !

    BEGIN
        I @ LEN @ <
    WHILE
        I @ ARR_GET 48 + WRITE_CHAR

        I @ 1 + I !
    REPEAT
;

ei
READ_LIST
di

SORT
PRINT_LIST