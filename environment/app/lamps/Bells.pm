package Bells;
use strict;
use warnings;

sub choose_bell {
    my ($bells, $severity, $color, $in_grace) = @_;
    for my $b (@$bells) {
        return ($b->{bell_name}, undef)
          if $b->{severity} eq $severity && $b->{color} eq $color;
    }
    return ('CHIME', undef);
}

1;
