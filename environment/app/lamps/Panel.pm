package Panel;
use strict;
use warnings;

sub read_lines {
    my ($path) = @_;
    open my $fh, '<:raw', $path or die "cannot read $path: $!";
    my @lines = <$fh>;
    close $fh;
    for (@lines) { s/\r?\n\z//; }
    return @lines;
}

sub read_tsv {
    my ($path) = @_;
    my @lines = grep { $_ ne '' && $_ !~ /^\s*#/ } read_lines($path);
    die "empty tsv $path" unless @lines;
    my @header = split /\t/, shift @lines, -1;
    my @rows;
    for my $line (@lines) {
        my @cols = split /\t/, $line, -1;
        my %row;
        for my $i (0 .. $#header) {
            $row{ $header[$i] } = $cols[$i] // '';
        }
        push @rows, \%row;
    }
    return \@header, \@rows;
}

sub load_clock {
    my ($panel) = @_;
    my @lines = grep { $_ ne '' && $_ !~ /^\s*#/ } read_lines("$panel/clock.txt");
    die "bad clock" unless @lines == 1;
    my ($minute, $id) = split /\s+/, $lines[0], 3;
    return { minute => 0 + $minute, clock_id => $id };
}

sub load_panel {
    my ($panel) = @_;
    my $clock = load_clock($panel);
    my (undef, $lamps) = read_tsv("$panel/lamps.tsv");
    my (undef, $flaps) = read_tsv("$panel/flaps.tsv");
    my (undef, $acks) = read_tsv("$panel/acknowledgements.tsv");
    my (undef, $blackouts) = read_tsv("$panel/blackouts.tsv");
    my (undef, $corridors) = read_tsv("$panel/corridors.tsv");
    my (undef, $bells) = read_tsv("$panel/bells.tsv");
    my (undef, $promotions) = read_tsv("$panel/promotions.tsv");
    my (undef, $operators) = read_tsv("$panel/operators.tsv");
    my (undef, $widths) = read_tsv("$panel/widths.tsv");
    return {
        clock      => $clock,
        lamps      => $lamps,
        flaps      => $flaps,
        acks       => $acks,
        blackouts  => $blackouts,
        corridors  => $corridors,
        bells      => $bells,
        promotions => $promotions,
        operators  => $operators,
        widths     => $widths,
        force_fail => -f "$panel/FORCE_FAIL",
    };
}

1;
