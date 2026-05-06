INCLUDE s"libs/math.fs"

VAR 100 N
VAR 0 I
VAR 0 SUM
VAR 0 SUMSQ
VAR 0 RESULT

: WRITE_NUMBER_RAW ( n -- )
    13 !
;

: SOLVE ( -- )
    1 I !
    0 SUM !
    0 SUMSQ !

    BEGIN
        I @ N @ <=
    WHILE
        SUM @ I @ +
        SUM !

        SUMSQ @ I @ I @ * +
        SUMSQ !

        I @ 1 +
        I !
    REPEAT

    SUM @ SUM @ *
    SUMSQ @ -
    RESULT !
;

SOLVE
RESULT @ WRITE_NUMBER_RAW