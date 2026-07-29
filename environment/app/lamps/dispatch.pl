#!/usr/bin/env perl
use strict;
use warnings;
use File::Path qw(make_path);

use Panel;
use Flaps;
use Blackout;
use Routes;
use Bells;
use Render;

my ($panel_dir, $out_dir) = @ARGV;
die "usage: dispatch.pl PANEL OUT\n" unless defined $panel_dir && defined $out_dir;

make_path($out_dir) unless -d $out_dir;
unlink "$out_dir/beacon.queue";
unlink "$out_dir/runner.fold";

if (-f "$panel_dir/FORCE_FAIL") {
    exit 1;
}

my $data = eval { Panel::load_panel($panel_dir) };
if (!$data) {
    exit 0;
}

my $minute = $data->{clock}{minute};
my ($widths, $hop) = Render::width_map($data->{widths});
$hop = 0 unless defined $hop;
my %lamps = map { $_->{lamp_id} => $_ } @{ $data->{lamps} };
my $collapsed = Flaps::collapse($data->{flaps});

my @beacons;
for my $alarm (@$collapsed) {
    next unless $alarm->{first_minute} <= $minute && $minute <= $alarm->{last_minute};
    my $lamp = $lamps{ $alarm->{lamp_id} } // next;
    my $zone = Blackout::zone_for_pos($data->{blackouts}, 0 + $lamp->{rack_pos});
    my $in_grace = 0;
    for my $a (@{ $data->{acks} }) {
        next unless $a->{flap_id} eq ($alarm->{flap_ids}[0] // '');
        my $ack = 0 + $a->{ack_minute};
        my $g = 0 + $a->{grace_minutes};
        $in_grace = 1 if $ack <= $minute && $minute <= $ack + $g;
    }
    my ($bell) = Bells::choose_bell($data->{bells}, $alarm->{severity}, $lamp->{color}, $in_grace);
    my $route = Routes::shortest_for_location($data->{corridors}, $lamp->{location});
    push @beacons, {
        lamp_id       => $alarm->{lamp_id},
        color         => $lamp->{color},
        zone_id       => $zone->{zone_id},
        age           => '' . ($minute - $alarm->{first_minute}),
        bell          => $bell,
        blackout      => (0 + ($zone->{masked} // 0)) ? 'MASKED' : 'CLEAR',
        message       => $alarm->{raw_text},
        silence_group => $lamp->{silence_group},
        route         => $route,
        location      => $lamp->{location},
    };
}

my %group_mask;
$group_mask{ $_->{silence_group} } = 1 for grep { $_->{blackout} eq 'MASKED' } @beacons;
my %best;
my %keep;
for my $b (sort { $a->{lamp_id} cmp $b->{lamp_id} } @beacons) {
    my $g = $b->{silence_group};
    if ($group_mask{$g}) {
        $best{$g} = $b->{lamp_id} if !exists $best{$g};
    }
    else {
        $keep{ $b->{lamp_id} } = $b;
    }
}
for my $b (@beacons) {
    my $g = $b->{silence_group};
    $keep{ $b->{lamp_id} } = $b if $group_mask{$g} && ($best{$g} // '') eq $b->{lamp_id};
}
@beacons = sort { $a->{lamp_id} cmp $b->{lamp_id} } values %keep;

my @blines = ( Render::beacon_header($widths) );
push @blines, Render::beacon_row($widths, $_) for @beacons;
my @rlines = ( Render::runner_header($widths) );
for my $b (@beacons) {
    my $r = $b->{route};
    push @rlines, Render::runner_row(
        $widths,
        {
            runner_id => $r->{runner_id},
            lamp_id   => $b->{lamp_id},
            path      => $r->{path},
            travel    => '' . $r->{travel},
            handoff   => '' . ($minute + $r->{travel}),
            note      => 'DELIVER',
        }
    );
}

Render::write_product("$out_dir/beacon.queue", @blines);
Render::write_product("$out_dir/runner.fold", @rlines);
exit 0;
