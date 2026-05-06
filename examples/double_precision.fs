INCLUDE s"libs/io.fs"

\ в результате сложения получим
\ 0x00000000_FFFFFFFF + 0x00000000_00000001 = 0x00000001_00000000

VAR 0 A_HI
VAR -1 A_LO \ это 0xFFFFFFFF

VAR 0 B_HI
VAR 1 B_LO

VAR 0 R_HI
VAR 0 R_LO
VAR 0 CARRY

: WRITE_NUMBER_RAW ( n -- )
    13 !
;

: ADD64 ( -- )
    A_LO @ B_LO @ +
    R_LO !

    push_flags CF &
    CARRY !

    A_HI @ B_HI @ +
    CARRY @ +
    R_HI !
;

ADD64

R_HI @ WRITE_NUMBER_RAW
R_LO @ WRITE_NUMBER_RAW