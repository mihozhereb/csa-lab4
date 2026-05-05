INCLUDE s"libs/io.fs"

ei

BEGIN
    READ_CHAR
    dup
WHILE
    WRITE_CHAR
REPEAT

drop
di