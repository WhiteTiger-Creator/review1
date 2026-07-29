package Routes;
use strict;
use warnings;

sub shortest_for_location {
    my ($corridors, $location) = @_;
    for my $c (@$corridors) {
        if ($c->{from_node} eq 'NOC' && $c->{to_node} eq $location) {
            return {
                runner_id => $c->{runner_id},
                travel    => 0 + $c->{travel_minutes},
                path      => "NOC>$location",
            };
        }
    }
    return {
        runner_id => 'R?',
        travel    => 0,
        path      => "NOC>$location",
    };
}

1;
