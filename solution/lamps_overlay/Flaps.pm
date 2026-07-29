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
                flap_ids           => [ $f->{flap_id} ],
                lamp_id            => $f->{lamp_id},
                first_minute       => 0 + $f->{first_minute},
                last_minute        => 0 + $f->{last_minute},
                primary_last_minute => 0 + $f->{last_minute},
                severity           => $f->{severity},
                raw_text           => $f->{raw_text},
                clock_id           => $f->{clock_id},
                primary_id         => $f->{flap_id},
            };
            next;
        }
        my $c = $by_key{$key};
        push @{ $c->{flap_ids} }, $f->{flap_id};
        my $first = 0 + $f->{first_minute};
        my $last  = 0 + $f->{last_minute};
        if ($first < $c->{first_minute}
            || ($first == $c->{first_minute} && $f->{flap_id} lt $c->{primary_id}))
        {
            $c->{first_minute}        = $first;
            $c->{primary_last_minute} = $last;
            $c->{severity}            = $f->{severity};
            $c->{primary_id}          = $f->{flap_id};
            $c->{clock_id}            = $f->{clock_id};
        }
        $c->{last_minute} = $last if $last > $c->{last_minute};
    }
    return [ values %by_key ];
}

sub active_alarms {
    my ($collapsed, $panel_minute) = @_;
    my @active;
    for my $c (@$collapsed) {
        next unless $c->{first_minute} <= $panel_minute && $panel_minute < $c->{last_minute};
        push @active, {
            %$c,
            age      => $panel_minute - $c->{first_minute},
            span_age => $c->{primary_last_minute} - $c->{first_minute},
        };
    }
    return \@active;
}

sub grace_active {
    my ($alarm, $acks, $panel_minute, $flap_first) = @_;
    my %ids = map { $_ => 1 } @{ $alarm->{flap_ids} };
    my @eligible;
    for my $a (@$acks) {
        next unless $ids{ $a->{flap_id} };
        my $ack = 0 + $a->{ack_minute};
        next unless $ack <= $panel_minute;
        my $fid = $a->{flap_id};
        if ($fid ne $alarm->{primary_id}) {
            my $own = 0 + ($flap_first->{$fid} // 0);
            next unless $ack >= $own;
        }
        push @eligible, $a;
    }
    return 0 unless @eligible;
    @eligible = sort {
        (0 + $b->{ack_minute}) <=> (0 + $a->{ack_minute})
          || (0 + $b->{grace_minutes}) <=> (0 + $a->{grace_minutes})
          || $b->{flap_id} cmp $a->{flap_id}
    } @eligible;
    my $chosen = $eligible[0];
    my $ack    = 0 + $chosen->{ack_minute};
    my $grace  = 0 + $chosen->{grace_minutes};
    return 1 if $grace > 0 && $ack <= $panel_minute && $panel_minute < $ack + $grace;
    return 0;
}

1;
