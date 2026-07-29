package Bells;
use strict;
use warnings;

sub _pick {
    my ($rows) = @_;
    die "no bell" unless @$rows;
    my $best_p;
    for my $r (@$rows) {
        my $p = 0 + $r->{priority};
        $best_p = $p if !defined $best_p || $p < $best_p;
    }
    my @tied = grep { 0 + $_->{priority} == $best_p } @$rows;
    if (@tied > 1) {
        my %rules = map { $_->{tie_rule} => 1 } @tied;
        my $rule = $tied[0]{tie_rule};
        die "bell tie" if keys %rules != 1 || !defined $rule || $rule eq '' || $rule eq '-';
        @tied = sort { $a->{bell_name} cmp $b->{bell_name} } @tied;
        return ($tied[0]{bell_name}, $rule);
    }
    return ($tied[0]{bell_name}, undef);
}

sub choose_bell {
    my ($bells, $severity, $color, $in_grace) = @_;
    my @rows;
    if ($in_grace) {
        @rows = grep { $_->{color} eq $color } @$bells;
    }
    else {
        @rows = grep { $_->{severity} eq $severity && $_->{color} eq $color } @$bells;
    }
    return _pick(\@rows);
}

1;
