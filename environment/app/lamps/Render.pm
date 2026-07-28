package Render;
use strict;
use warnings;

sub width_map {
    my ($rows) = @_;
    my %w;
    my $hop = 0;
    for my $r (@$rows) {
        if ($r->{field} eq 'hop_penalty') {
            $hop = 0 + $r->{width};
            next;
        }
        if ($r->{field} eq 'hold_surcharge') {
            next;
        }
        if ($r->{field} eq 'depth_penalty') {
            next;
        }
        if ($r->{field} eq 'hop_waiver') {
            next;
        }
        $w{ $r->{field} } = 0 + $r->{width};
    }
    return (\%w, $hop);
}

sub pad {
    my ($text, $width) = @_;
    $text = '' unless defined $text;
    $width = 8 if !defined $width || $width <= 0;
    if (length($text) > $width) {
        return substr($text, 0, $width);
    }
    return $text . (' ' x ($width - length($text)));
}

sub beacon_header {
    my ($w) = @_;
    return join '',
      pad('LAMP',     $w->{beacon_lamp} // 8),
      pad('COLOR',    $w->{beacon_color} // 8),
      pad('ZONE',     $w->{beacon_zone} // 8),
      pad('AGE',      $w->{beacon_age} // 6),
      pad('BELL',     $w->{beacon_bell} // 12),
      pad('BLACKOUT', $w->{beacon_blackout} // 10),
      pad('MESSAGE',  $w->{beacon_message} // 40);
}

sub beacon_row {
    my ($w, $row) = @_;
    return join '',
      pad($row->{lamp_id},  $w->{beacon_lamp} // 8),
      pad($row->{color},    $w->{beacon_color} // 8),
      pad($row->{zone_id},  $w->{beacon_zone} // 8),
      pad($row->{age},      $w->{beacon_age} // 6),
      pad($row->{bell},     $w->{beacon_bell} // 12),
      pad($row->{blackout}, $w->{beacon_blackout} // 10),
      pad($row->{message},  $w->{beacon_message} // 40);
}

sub runner_header {
    my ($w) = @_;
    return join '',
      pad('RUNNER',  $w->{runner_id} // 8),
      pad('LAMP',    $w->{runner_lamp} // 8),
      pad('PATH',    $w->{runner_path} // 48),
      pad('TRAVEL',  $w->{runner_travel} // 6),
      pad('HANDOFF', $w->{runner_handoff} // 8),
      pad('NOTE',    $w->{runner_note} // 24);
}

sub runner_row {
    my ($w, $row) = @_;
    return join '',
      pad($row->{runner_id}, $w->{runner_id} // 8),
      pad($row->{lamp_id},   $w->{runner_lamp} // 8),
      pad($row->{path},      $w->{runner_path} // 48),
      pad($row->{travel},    $w->{runner_travel} // 6),
      pad($row->{handoff},   $w->{runner_handoff} // 8),
      pad($row->{note},      $w->{runner_note} // 24);
}

sub write_product {
    my ($path, @lines) = @_;
    open my $fh, '>:raw', $path or die "write $path: $!";
    print {$fh} map { "$_\n" } @lines;
    close $fh;
}

1;
