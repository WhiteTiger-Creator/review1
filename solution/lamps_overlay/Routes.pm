package Routes;
use strict;
use warnings;

sub _per_runner_paths {
    my ($corridors) = @_;
    my %by_runner;
    for my $c (@$corridors) {
        my $mins = 0 + $c->{travel_minutes};
        die "negative travel" if $mins < 0;
        push @{ $by_runner{ $c->{runner_id} } },
          [ $c->{from_node}, $c->{to_node}, $mins ];
    }
    return \%by_runner;
}

sub _best_path_for_runner {
    my ($edges, $location) = @_;
    my %best;
    for my $e (@$edges) {
        my $k = $e->[0] . "\0" . $e->[1];
        if (!exists $best{$k} || $e->[2] < $best{$k}[2]) {
            $best{$k} = $e;
        }
    }
    my %graph;
    for my $e (values %best) {
        push @{ $graph{ $e->[0] } }, [ $e->[1], $e->[2] ];
    }
    my %dist = ( NOC => 0 );
    my %path = ( NOC => 'NOC' );
    my @q = ('NOC');
    my %in = ( NOC => 1 );
    while (@q) {
        @q = sort { $dist{$a} <=> $dist{$b} || $a cmp $b } @q;
        my $u = shift @q;
        delete $in{$u};
        for my $edge (@{ $graph{$u} // [] }) {
            my ($v, $w) = @$edge;
            my $nd = $dist{$u} + $w;
            my $np = $path{$u} . '>' . $v;
            my $nh = () = $np =~ />/g;
            my $oh = exists $path{$v} ? (() = $path{$v} =~ />/g) : 10_000;
            if (!exists $dist{$v} || $nd < $dist{$v}
                || ($nd == $dist{$v} && ($nh < $oh
                    || ($nh == $oh && $np lt ($path{$v} // "\x{ff}")))))
            {
                $dist{$v} = $nd;
                $path{$v} = $np;
                if (!$in{$v}) {
                    push @q, $v;
                    $in{$v} = 1;
                }
            }
        }
    }
    return undef unless exists $dist{$location};
    my $pp = $path{$location};
    my $hops = () = $pp =~ />/g;
    return {
        travel => $dist{$location},
        path   => $pp,
        hops   => $hops,
    };
}

# Pick route: per-runner travel-best path, then across runners by handoff score.
sub route_for_beacon {
    my (
        $corridors, $location, $minute, $hop_penalty, $hop_waiver,
        $hold_tax, $depth_tax
    ) = @_;
    my $by_runner = _per_runner_paths($corridors);
    my @candidates;
    for my $runner (sort keys %$by_runner) {
        my $best = _best_path_for_runner($by_runner->{$runner}, $location);
        next unless defined $best;
        my $billed = $best->{hops} - $hop_waiver;
        $billed = 0 if $billed < 0;
        my $handoff =
          $minute + $best->{travel} + $billed * $hop_penalty + $hold_tax + $depth_tax;
        push @candidates, {
            runner_id => $runner,
            travel    => $best->{travel},
            path      => $best->{path},
            hops      => $best->{hops},
            handoff   => $handoff,
        };
    }
    die "dead end" unless @candidates;
    @candidates = sort {
        $a->{handoff} <=> $b->{handoff}
          || $a->{runner_id} cmp $b->{runner_id}
          || $a->{path} cmp $b->{path}
    } @candidates;
    return $candidates[0];
}

# Back-compat alias used by smoke/starter paths (travel-only ranking).
sub shortest_for_location {
    my ($corridors, $location) = @_;
    return route_for_beacon($corridors, $location, 0, 0, 0, 0, 0);
}

1;
