package Promote;
use strict;
use warnings;

my %LOUD = ( HIGH => 3, MED => 2, LOW => 1 );

sub promote {
    my ($promotions, $severity, $age, $in_grace) = @_;
    return $severity if $in_grace;
    my @cands;
    for my $p (@$promotions) {
        my $th = 0 + $p->{age_threshold};
        die "bad promo" if $th < 0;
        my $from = $p->{severity_from};
        my $to   = $p->{severity_to};
        die "bad promo sev" unless exists $LOUD{$from} && exists $LOUD{$to};
        next unless $from eq $severity;
        next unless $age > $th;
        push @cands, $p;
    }
    return $severity unless @cands;
    @cands = sort {
        (0 + $b->{age_threshold}) <=> (0 + $a->{age_threshold})
          || $LOUD{ $a->{severity_to} } <=> $LOUD{ $b->{severity_to} }
    } @cands;
    return $cands[0]{severity_to};
}

1;
