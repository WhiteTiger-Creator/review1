package Flaps;
use strict;
use warnings;

sub collapse {
    my ($flaps) = @_;
    my %by_key;
    for my $f (@$flaps) {
        my $key = $f->{lamp_id} . "\0" . $f->{raw_text};
        if (!exists $by_key{$key}) {
            $by_key{$key} = {
                flap_ids     => [ $f->{flap_id} ],
                lamp_id      => $f->{lamp_id},
                first_minute => 0 + $f->{first_minute},
                last_minute  => 0 + $f->{last_minute},
                severity     => $f->{severity},
                raw_text     => $f->{raw_text},
                clock_id     => $f->{clock_id},
            };
            next;
        }
        my $c = $by_key{$key};
        my $last = 0 + $f->{last_minute};
        $c->{last_minute} = $last if $last > $c->{last_minute};
        my $first = 0 + $f->{first_minute};
        $c->{first_minute} = $first if $first < $c->{first_minute};
    }
    return [ values %by_key ];
}

1;
