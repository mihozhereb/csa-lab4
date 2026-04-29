: NF ( -- mask ) 8 ;
: ZF ( -- mask ) 4 ;
: VF ( -- mask ) 2 ;
: CF ( -- mask ) 1 ;

: ++ ( a -- a+1 ) 1 + ;
: -- ( a -- a-1 ) 1 - ;
: NEG ( a -- -a ) 0 swap - ;

: == ( a b -- flag ) - push_flags ZF & ;
: 0= ( a -- flag ) 0 - push_flags ZF & ;
: != ( a b -- flag ) == 0= ;

: < ( a b -- flag ) - push_flags dup NF & swap VF & ^ ;
: >= ( a b -- flag ) < 0= ;
: > ( a b -- flag ) swap < ;
: <= ( a b -- flag ) > 0= ;

: 1+ ( a -- a+1 ) 1 + ;
: 1- ( a -- a-1 ) 1 - ;
: 2dup ( a b -- a b a b ) over over ;
: 2drop ( a b -- ) drop drop ;
: NOT ( a -- flag ) 0= ;
: 0> ( a -- flag ) 0 > ;
: 0< ( a -- flag ) 0 < ;