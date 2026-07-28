package Render;
use strict;
use warnings;

sub width_map {
    my ($rows) = @_;
    my %w;
    my $hop;
    my $waiver;
    my $hold;
    my $depth;
    for my $r (@$rows) {
        my $field = $r->{field};
        my $n = 0 + $r->{width};
        if ($field eq 'hop_penalty') {
            die "bad hop" if $n < 0;
            $hop = $n;
            next;
        }
        if ($field eq 'hop_waiver') {
            die "bad waiver" if $n < 0;
            $waiver = $n;
            next;
        }
        if ($field eq 'hold_surcharge') {
            die "bad hold" if $n < 0;
            $hold = $n;
            next;
        }
        if ($field eq 'depth_penalty') {
            die "bad depth" if $n < 0;
            $depth = $n;
            next;
        }
        die "bad width" if $n <= 0;
        $w{$field} = $n;
    }
    die "missing hop" unless defined $hop;
    die "missing waiver" unless defined $waiver;
    die "missing hold" unless defined $hold;
    die "missing depth" unless defined $depth;
    my @need = qw(
      beacon_lamp beacon_color beacon_zone beacon_age beacon_bell beacon_blackout beacon_message
      runner_id runner_lamp runner_path runner_travel runner_handoff runner_note
    );
    for my $k (@need) {
        die "missing width $k" unless exists $w{$k};
    }
    return (\%w, $hop, $waiver, $hold, $depth);
}

sub pad {
    my ($text, $width) = @_;
    $text = '' unless defined $text;
    die "overflow" if length($text) > $width;
    return $text . (' ' x ($width - length($text)));
}

sub beacon_header {
    my ($w) = @_;
    return join '',
      pad('LAMP',     $w->{beacon_lamp}),
      pad('COLOR',    $w->{beacon_color}),
      pad('ZONE',     $w->{beacon_zone}),
      pad('AGE',      $w->{beacon_age}),
      pad('BELL',     $w->{beacon_bell}),
      pad('BLACKOUT', $w->{beacon_blackout}),
      pad('MESSAGE',  $w->{beacon_message});
}

sub beacon_row {
    my ($w, $row) = @_;
    return join '',
      pad($row->{lamp_id},   $w->{beacon_lamp}),
      pad($row->{color},     $w->{beacon_color}),
      pad($row->{zone_id},   $w->{beacon_zone}),
      pad($row->{age},       $w->{beacon_age}),
      pad($row->{bell},      $w->{beacon_bell}),
      pad($row->{blackout},  $w->{beacon_blackout}),
      pad($row->{message},   $w->{beacon_message});
}

sub runner_header {
    my ($w) = @_;
    return join '',
      pad('RUNNER',  $w->{runner_id}),
      pad('LAMP',    $w->{runner_lamp}),
      pad('PATH',    $w->{runner_path}),
      pad('TRAVEL',  $w->{runner_travel}),
      pad('HANDOFF', $w->{runner_handoff}),
      pad('NOTE',    $w->{runner_note});
}

sub runner_row {
    my ($w, $row) = @_;
    return join '',
      pad($row->{runner_id}, $w->{runner_id}),
      pad($row->{lamp_id},   $w->{runner_lamp}),
      pad($row->{path},      $w->{runner_path}),
      pad($row->{travel},    $w->{runner_travel}),
      pad($row->{handoff},   $w->{runner_handoff}),
      pad($row->{note},      $w->{runner_note});
}

sub write_product {
    my ($path, @lines) = @_;
    open my $fh, '>:raw', $path or die "write $path: $!";
    print {$fh} map { "$_\n" } @lines;
    close $fh;
}

1;
