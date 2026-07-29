#!/usr/bin/env perl
use strict;
use warnings;
use File::Path qw(make_path remove_tree);
use Cwd qw(abs_path);

use Panel;
use Flaps;
use Blackout;
use Routes;
use Bells;
use Promote;
use Render;

my ($panel_dir, $out_dir) = @ARGV;
die "usage: dispatch.pl PANEL OUT\n" unless defined $panel_dir && defined $out_dir;

sub clean_notes {
    my $notes = '/app/notes';
    return unless -d $notes;
    opendir my $dh, $notes or return;
    while (my $name = readdir $dh) {
        next if $name eq '.' || $name eq '..' || $name eq '.keep';
        my $path = "$notes/$name";
        if (-d $path) {
            remove_tree($path);
        }
        else {
            unlink $path;
        }
    }
    closedir $dh;
}

sub scrub_out {
    my ($dir, @keep) = @_;
    return unless defined $dir && -d $dir;
    my %keep = map { $_ => 1 } @keep;
    $keep{'.keep'} = 1;
    opendir my $dh, $dir or return;
    while (my $name = readdir $dh) {
        next if $name eq '.' || $name eq '..';
        next if $keep{$name};
        my $path = "$dir/$name";
        if (-d $path) {
            remove_tree($path);
        }
        else {
            unlink $path;
        }
    }
    closedir $dh;
}

sub ensure_keep {
    my ($dir) = @_;
    return unless defined $dir && -d $dir;
    my $keep = "$dir/.keep";
    return if -f $keep;
    open my $fh, '>', $keep or return;
    print {$fh} "\n";
    close $fh;
}

sub resolve_out {
    my ($raw) = @_;
    make_path($raw) unless -d $raw;
    my $abs = abs_path($raw);
    die "bad out" unless defined $abs;
    my $root = abs_path('/app/out');
    die "out escape" unless defined $root;
    die "out escape" unless $abs eq $root || index($abs, $root . '/') == 0;
    return $abs;
}

my $ok = eval {
    my $out = resolve_out($out_dir);
    scrub_out($out);
    ensure_keep($out);

    make_path('/app/notes');
    open my $nf, '>', '/app/notes/scratch.tmp' or die $!;
    print {$nf} "working\n";
    close $nf;

    die "forced" if -f "$panel_dir/FORCE_FAIL";

    my $data = Panel::load_panel($panel_dir);
    my $minute = $data->{clock}{minute};
    my $clock_id = $data->{clock}{clock_id};

    my %lamps;
    for my $l (@{ $data->{lamps} }) {
        die "dup lamp" if exists $lamps{ $l->{lamp_id} };
        $lamps{ $l->{lamp_id} } = $l;
    }

    for my $f (@{ $data->{flaps} }) {
        die "clock" unless $f->{clock_id} eq $clock_id;
        die "unknown lamp" unless exists $lamps{ $f->{lamp_id} };
        die "bad window" if 0 + $f->{first_minute} > 0 + $f->{last_minute};
    }
    my %flap_ids = map { $_->{flap_id} => 1 } @{ $data->{flaps} };
    my %ops;
    for my $o (@{ $data->{operators} }) {
        die "dup op" if exists $ops{ $o->{operator_id} };
        $ops{ $o->{operator_id} } = 1;
    }
    for my $a (@{ $data->{acks} }) {
        die "clock" unless $a->{clock_id} eq $clock_id;
        die "unknown ack" unless $flap_ids{ $a->{flap_id} };
        die "unknown op" unless $ops{ $a->{operator_id} };
    }

    my $zones = Blackout::build_zones($data->{blackouts});
    my ($widths, $hop_penalty, $hop_waiver, $hold_surcharge, $depth_penalty) =
      Render::width_map($data->{widths});

    my $collapsed = Flaps::collapse($data->{flaps});
    for my $c (@$collapsed) {
        for my $a (@{ $data->{acks} }) {
            my %ids = map { $_ => 1 } @{ $c->{flap_ids} };
            next unless $ids{ $a->{flap_id} };
            die "early ack" if 0 + $a->{ack_minute} < $c->{first_minute};
        }
    }

    my $active = Flaps::active_alarms($collapsed, $minute);
    my %flap_first = map { $_->{flap_id} => 0 + $_->{first_minute} } @{ $data->{flaps} };

    my @beacons;
    for my $alarm (@$active) {
        my $lamp = $lamps{ $alarm->{lamp_id} };
        my $zone = Blackout::zone_for_pos($zones, 0 + $lamp->{rack_pos});
        my $masked = Blackout::inherited_masked($zones, $zone);
        my $local_mask = $zone->{masked} ? 1 : 0;
        my $mdepth = Blackout::masked_depth($zones, $zone);
        my $in_grace = Flaps::grace_active($alarm, $data->{acks}, $minute, \%flap_first);
        my $sev = Promote::promote(
            $data->{promotions}, $alarm->{severity}, $alarm->{span_age}, $in_grace
        );
        my ($bell, $tie) = Bells::choose_bell(
            $data->{bells}, $sev, $lamp->{color}, $in_grace
        );
        my $msg = $alarm->{raw_text};
        $msg = '*' . $msg if $local_mask;
        $msg .= "[tie:$tie]" if defined $tie;
        push @beacons, {
            lamp_id       => $alarm->{lamp_id},
            color         => $lamp->{color},
            zone_id       => $zone->{zone_id},
            age           => '' . $alarm->{age},
            age_num       => 0 + $alarm->{age},
            bell          => $bell,
            blackout      => $masked ? 'MASKED' : 'CLEAR',
            message       => $msg,
            silence_group => $lamp->{silence_group},
            location      => $lamp->{location},
            local_mask    => $local_mask,
            masked_depth  => $mdepth,
            in_grace      => $in_grace ? 1 : 0,
        };
    }

    for my $b (@beacons) {
        die "overflow" if length($b->{message}) > $widths->{beacon_message};
    }

    my %group_has_mask;
    for my $b (@beacons) {
        $group_has_mask{ $b->{silence_group} } = 1 if $b->{blackout} eq 'MASKED';
    }
    my %group_has_local;
    for my $b (@beacons) {
        $group_has_local{ $b->{silence_group} } = 1
          if $b->{blackout} eq 'MASKED' && $b->{local_mask};
    }
    my %keep;
    my %best_masked;
    for my $b (@beacons) {
        my $g = $b->{silence_group};
        if (!$group_has_mask{$g}) {
            $keep{ $b->{lamp_id} } = $b;
            next;
        }
        # Inherited-only MASKED does not suppress CLEAR peers.
        if ($b->{blackout} eq 'CLEAR') {
            if (!$group_has_local{$g}) {
                $keep{ $b->{lamp_id} } = $b;
            }
            next;
        }
        next unless $b->{blackout} eq 'MASKED';
        if ($group_has_local{$g} && !$b->{local_mask}) {
            next;
        }
        if (!exists $best_masked{$g}
            || $b->{age_num} > $best_masked{$g}{age_num}
            || ($b->{age_num} == $best_masked{$g}{age_num}
                && $b->{lamp_id} lt $best_masked{$g}{lamp_id}))
        {
            $best_masked{$g} = $b;
        }
    }
    for my $b (@beacons) {
        my $g = $b->{silence_group};
        if ($b->{blackout} eq 'MASKED'
            && exists $best_masked{$g}
            && $best_masked{$g}{lamp_id} eq $b->{lamp_id})
        {
            $keep{ $b->{lamp_id} } = $b;
        }
    }
    @beacons = sort {
        $b->{age_num} <=> $a->{age_num}
          || ($a->{blackout} eq 'MASKED' ? 0 : 1) <=> ($b->{blackout} eq 'MASKED' ? 0 : 1)
          || $a->{lamp_id} cmp $b->{lamp_id}
    } values %keep;

    my @runners;
    for my $b (@beacons) {
        my $hold_tax = 0;
        if ($b->{blackout} eq 'MASKED' && !$b->{in_grace}) {
            $hold_tax = $hold_surcharge;
        }
        my $depth_tax = $b->{local_mask} ? $b->{masked_depth} * $depth_penalty : 0;
        my $route = Routes::route_for_beacon(
            $data->{corridors}, $b->{location}, $minute,
            $hop_penalty, $hop_waiver, $hold_tax, $depth_tax
        );
        my $note = $b->{local_mask} ? 'MASK-HOLD' : 'DELIVER';
        push @runners, {
            runner_id => $route->{runner_id},
            lamp_id   => $b->{lamp_id},
            path      => $route->{path},
            travel    => '' . $route->{travel},
            handoff   => '' . $route->{handoff},
            note      => $note,
        };
    }
    @runners = sort {
        $a->{handoff} <=> $b->{handoff}
          || $a->{runner_id} cmp $b->{runner_id}
          || $a->{path} cmp $b->{path}
          || $a->{lamp_id} cmp $b->{lamp_id}
    } @runners;

    my @blines = ( Render::beacon_header($widths) );
    push @blines, Render::beacon_row($widths, $_) for @beacons;
    my @rlines = ( Render::runner_header($widths) );
    push @rlines, Render::runner_row($widths, $_) for @runners;

    Render::write_product("$out/beacon.queue", @blines);
    Render::write_product("$out/runner.fold", @rlines);
    scrub_out($out, 'beacon.queue', 'runner.fold');
    ensure_keep($out);
    clean_notes();
    1;
};

if (!$ok) {
    my $msg = $@ || 'dispatch failed';
    eval {
        my $out = resolve_out($out_dir);
        scrub_out($out);
        ensure_keep($out);
    };
    clean_notes();
    print STDERR "dispatch-error: $msg\n";
    exit 1;
}

exit 0;
