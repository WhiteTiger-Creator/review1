package Blackout;
use strict;
use warnings;

sub zone_for_pos {
    my ($rows, $pos) = @_;
    for my $z (@$rows) {
        return $z if 0 + $z->{rack_lo} <= $pos && $pos <= 0 + $z->{rack_hi};
    }
    return { zone_id => '?', masked => 0, parent_id => '-' };
}

1;
