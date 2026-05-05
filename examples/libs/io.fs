INCLUDE s"math.fs"

VAR 0 INPUT_READY
VAR 0 INPUT_VALUE

VAR 0 STR_ADDR
VAR 0 STR_MAX
VAR 0 STR_LEN
VAR 0 STR_CHAR
VAR 0 STR_DONE

: IO_IN ( -- addr ) 9 ;
: IO_OUT ( -- addr ) 13 ;

: interruption_handler ( -- )
    IO_IN @
    INPUT_VALUE !
    1 INPUT_READY ! ;

: WAIT_INPUT ( -- )
    BEGIN
        INPUT_READY @ 0=
    WHILE
    REPEAT ;

: READ_CHAR ( -- char )
    WAIT_INPUT
    0 INPUT_READY !
    INPUT_VALUE @ ;

: WRITE_CHAR ( char -- )
    IO_OUT ! ;

: WRITE_STR ( addr -- )
    BEGIN
        dup @
    WHILE
        dup @
        WRITE_CHAR
        4 +
    REPEAT
    drop ;

: READ_STR ( addr max_len -- )
    STR_MAX !
    STR_ADDR !
    0 STR_LEN !
    0 STR_DONE !

    BEGIN
        STR_LEN @ STR_MAX @ 1 - <
        STR_DONE @ 0=
        &
    WHILE
        READ_CHAR
        STR_CHAR !

        STR_CHAR @ 0=
        IF
        1 STR_DONE !
        ELSE
        STR_CHAR @ STR_ADDR @ STR_LEN @ 4 * + !
        STR_LEN @ 1 + STR_LEN !
        THEN
    REPEAT

    0 STR_ADDR @ STR_LEN @ 4 * + ! ;
