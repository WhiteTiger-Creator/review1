package Blackout;
use strict;
use warnings;

sub build_zones {
    my ($rows) = @_;
    my %zones;
    for my $r (@$rows) {
        my $id = $r->{zone_id};
        die "dup zone" if exists $zones{$id};
        $zones{$id} = {
            zone_id   => $id,
            parent_id => $r->{parent_id},
            rack_lo   => 0 + $r->{rack_lo},
            rack_hi   => 0 + $r->{rack_hi},
            masked    => do {
                my $m = $r->{masked};
                die "bad mask" unless defined $m && $m =~ /^(0|1)$/;
                0 + $m;
            },
        };
    }
    for my $z (values %zones) {
        my $p = $z->{parent_id};
        next if $p eq '-';
        die "missing parent" unless exists $zones{$p};
    }
    for my $zid (keys %zones) {
        my %seen;
        my $cur = $zid;
        while (1) {
            die "cycle" if $seen{$cur}++;
            my $p = $zones{$cur}{parent_id};
            last if $p eq '-';
            die "missing parent" unless exists $zones{$p};
            $cur = $p;
        }
    }
    my @ids = sort keys %zones;
    for my $i (0 .. $#ids) {
        for my $j ($i + 1 .. $#ids) {
            my $a = $zones{ $ids[$i] };
            my $b = $zones{ $ids[$j] };
            my $overlap = !($a->{rack_hi} < $b->{rack_lo} || $b->{rack_hi} < $a->{rack_lo});
            die "overlap" if $overlap;
        }
    }
    return \%zones;
}

sub zone_for_pos {
    my ($zones, $pos) = @_;
    my @hits;
    for my $z (values %$zones) {
        push @hits, $z if $z->{rack_lo} <= $pos && $pos <= $z->{rack_hi};
    }
    die "no zone" unless @hits == 1;
    return $hits[0];
}

sub inherited_masked {
    my ($zones, $zone) = @_;
    my $cur = $zone;
    my %seen;
    while (1) {
        return 1 if $cur->{masked};
        my $p = $cur->{parent_id};
        last if $p eq '-';
        die "missing parent" unless exists $zones->{$p};
        die "cycle" if $seen{$p}++;
        $cur = $zones->{$p};
    }
    return 0;
}

sub zone_depth {
    my ($zones, $zone) = @_;
    my $depth = 0;
    my $cur   = $zone;
    my %seen;
    while (1) {
        my $p = $cur->{parent_id};
        last if $p eq '-';
        die "missing parent" unless exists $zones->{$p};
        die "cycle" if $seen{$p}++;
        $depth++;
        $cur = $zones->{$p};
    }
    return $depth;
}

sub masked_depth {
    my ($zones, $zone) = @_;
    my $depth = 0;
    my $cur   = $zone;
    my %seen;
    while (1) {
        $depth++ if $cur->{masked};
        my $p = $cur->{parent_id};
        last if $p eq '-';
        die "missing parent" unless exists $zones->{$p};
        die "cycle" if $seen{$p}++;
        $cur = $zones->{$p};
    }
    return $depth;
}

1;
