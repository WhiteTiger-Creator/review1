#!/usr/bin/env sh
set -eu

cat > /opt/pod-lock-desk/pod-source-lock <<'PERL'
#!/usr/bin/env perl
use strict;
use warnings;
use Digest::SHA qw(sha256_hex);
use File::Path qw(remove_tree make_path);

my $ROOT = "/opt/pod-lock-desk";
my $CASE = "$ROOT/case";
my $OUT = "$ROOT/out";

sub read_tsv {
    my ($path) = @_;
    open my $fh, "<", $path or die "cannot read $path: $!";
    chomp(my $header = <$fh>);
    my @cols = split /\t/, $header, -1;
    my @rows;
    while (defined(my $line = <$fh>)) {
        chomp $line;
        next if $line eq "";
        my @vals = split /\t/, $line, -1;
        my %row;
        for my $i (0 .. $#cols) {
            $row{$cols[$i]} = defined $vals[$i] ? $vals[$i] : "";
        }
        push @rows, \%row;
    }
    close $fh;
    return @rows;
}

sub list_values {
    my ($cell, $sep) = @_;
    return () if !defined($cell) || $cell eq "" || $cell eq "-";
    return grep { $_ ne "" } split /\Q$sep\E/, $cell;
}

sub vparts {
    my ($v) = @_;
    my @p = split /\./, $v;
    push @p, 0 while @p < 3;
    return map { int($_ || 0) } @p[0..2];
}

sub vcmp {
    my ($a, $b) = @_;
    my @a = vparts($a);
    my @b = vparts($b);
    for my $i (0..2) {
        return $a[$i] <=> $b[$i] if $a[$i] != $b[$i];
    }
    return 0;
}

sub satisfies {
    my ($version, $req) = @_;
    return 1 if !defined($req) || $req eq "" || $req eq "*" || $req eq "-";
    if ($req =~ /^~> (\d+)\.(\d+)\.(\d+)$/) {
        my $lo = "$1.$2.$3";
        my $hi = "$1." . ($2 + 1) . ".0";
        return vcmp($version, $lo) >= 0 && vcmp($version, $hi) < 0;
    }
    if ($req =~ /^~> (\d+)\.(\d+)$/) {
        my $lo = "$1.$2.0";
        my $hi = ($1 + 1) . ".0.0";
        return vcmp($version, $lo) >= 0 && vcmp($version, $hi) < 0;
    }
    if ($req =~ /^>=(\d+(?:\.\d+){0,2}) <(\d+(?:\.\d+){0,2})$/) {
        return vcmp($version, $1) >= 0 && vcmp($version, $2) < 0;
    }
    if ($req =~ /^>=(\d+(?:\.\d+){0,2})$/) {
        return vcmp($version, $1) >= 0;
    }
    if ($req =~ /^(\d+(?:\.\d+){0,2})$/) {
        return vcmp($version, $1) == 0;
    }
    return 0;
}

sub version_ge {
    my ($actual, $minimum) = @_;
    return vcmp($actual, $minimum) >= 0;
}

my %policy;
for my $r (read_tsv("$CASE/policy.tsv")) {
    $policy{$r->{key}} = $r->{value};
}
my @source_order = list_values($policy{source_order}, ",");
my %source_rank;
for my $i (0..$#source_order) {
    $source_rank{$source_order[$i]} = $i;
}

my @targets = read_tsv("$CASE/targets.tsv");
my @spec_rows = read_tsv("$CASE/specs.tsv");
my @rule_rows = read_tsv("$CASE/rules.tsv");

my %spec;
my %tuples;
for my $s (@spec_rows) {
    my $tk = join("|", $s->{source}, $s->{root}, $s->{version});
    $spec{$tk}{$s->{subspec}} = $s;
    $tuples{$s->{root}}{$tk} = { source => $s->{source}, root => $s->{root}, version => $s->{version} };
}

my %override;
my %source_block;
my %license_allow;
for my $r (@rule_rows) {
    if ($r->{kind} eq "override") {
        $override{$r->{root}} = $r->{value};
    } elsif ($r->{kind} eq "source_block") {
        $source_block{$r->{root}}{$r->{subspec}}{$r->{value}} = 1;
    } elsif ($r->{kind} eq "license_allow") {
        $license_allow{$_} = 1 for list_values($r->{value}, ",");
    }
}

sub tuple_key {
    my ($t) = @_;
    return join("|", $t->{source}, $t->{root}, $t->{version});
}

sub default_subspecs {
    my ($t) = @_;
    my $tk = tuple_key($t);
    my @subs = sort grep { $spec{$tk}{$_}{default} eq "true" } keys %{ $spec{$tk} || {} };
    return @subs;
}

sub parse_dep {
    my ($dep) = @_;
    my @p = split /\|/, $dep, -1;
    my ($root, $subs) = split /\//, $p[0], 2;
    return {
        root => $root,
        subspecs => defined($subs) && $subs ne "" ? $subs : "-",
        requirement => $p[1],
        source_pin => $p[2],
        checksum_required => $p[3],
    };
}

sub platform_ok {
    my ($row, $platform, $version) = @_;
    for my $p (list_values($row->{platforms}, ",")) {
        if ($p =~ /^([a-z]+)>=(\d+(?:\.\d+){0,2})$/) {
            return 1 if $1 eq $platform && version_ge($version, $2);
        }
    }
    return 0;
}

my @audit;
my @edges;
my %unsat;

sub add_audit {
    my (@fields) = @_;
    push @audit, [map { defined($_) ? "$_" : "" } @fields];
}

sub expand_subspecs {
    my ($t, $subspec_cell) = @_;
    return sort { $a cmp $b } default_subspecs($t) if !defined($subspec_cell) || $subspec_cell eq "" || $subspec_cell eq "-";
    return sort { $a cmp $b } list_values($subspec_cell, ",");
}

sub candidate_size {
    my ($t, $subs) = @_;
    my $tk = tuple_key($t);
    my $sum = 0;
    for my $sub (@$subs) {
        $sum += int($spec{$tk}{$sub}{size} || 0);
    }
    return $sum;
}

sub reject_tuple {
    my ($t, $version, $subspec, $reason, $detail) = @_;
    add_audit("rejected", $t->{root}, $t->{source}, $version, $subspec, "rejected", $reason, $detail);
}

sub evaluate_tuple {
    my ($t, $req) = @_;
    my $tk = tuple_key($t);
    return (0, [], "source", $t->{source}) if !exists $source_rank{$t->{source}};
    return (0, [], "source_pin", $req->{source_pin}) if $req->{source_pin} ne "-" && $req->{source_pin} ne $t->{source};
    return (0, [], "range", $req->{requirement}) if !satisfies($t->{version}, $req->{requirement});
    return (0, [], "source_block", $t->{source}) if $source_block{$t->{root}}{"*"}{$t->{source}};
    my @subs = expand_subspecs($t, $req->{subspecs});
    for my $sub (@subs) {
        return (0, \@subs, "source_block", $t->{source}) if $source_block{$t->{root}}{$sub}{$t->{source}};
    }
    for my $sub (@subs) {
        my $row = $spec{$tk}{$sub};
        return (0, \@subs, "missing_subspec", $sub) if !$row;
        return (0, \@subs, "platform", $req->{platform} . ">=" . $req->{platform_version}) if !platform_ok($row, $req->{platform}, $req->{platform_version});
        return (0, \@subs, "status", $row->{status}) if $row->{status} eq "deprecated";
        return (0, \@subs, "status", $row->{status}) if $row->{status} eq "prerelease" && $policy{allow_prerelease} ne "true";
        return (0, \@subs, "trust", $row->{trust}) if int($row->{trust}) < int($policy{min_trust});
        return (0, \@subs, "license", $row->{license}) if !exists $license_allow{$row->{license}};
        return (0, \@subs, "checksum", $sub) if $req->{checksum_required} eq "true" && $row->{checksum_present} ne "true";
    }
    return (1, \@subs, "", "");
}

sub candidate_cmp {
    my ($a, $b) = @_;
    my $vc = vcmp($b->{tuple}{version}, $a->{tuple}{version});
    return $vc if $vc;
    my $sr = ($source_rank{$a->{tuple}{source}} // 999) <=> ($source_rank{$b->{tuple}{source}} // 999);
    return $sr if $sr;
    return $a->{size} <=> $b->{size} if $a->{size} != $b->{size};
    return tuple_key($a->{tuple}) cmp tuple_key($b->{tuple});
}

sub normalize_target_request {
    my ($r) = @_;
    my $platform = $r->{platform} eq "-" ? $policy{platform} : $r->{platform};
    my $platform_version = $r->{platform_version} eq "-" ? $policy{platform_version} : $r->{platform_version};
    return {
        target => $r->{target},
        direct => 1,
        from => "target:$r->{target}",
        root => $r->{pod},
        requirement => $r->{requirement},
        original_requirement => $r->{requirement},
        subspecs => $r->{subspecs},
        configurations => $r->{configurations},
        linkage => $r->{linkage},
        source_pin => $r->{source_pin},
        checksum_required => $r->{checksum_required},
        platform => $platform,
        platform_version => $platform_version,
        reason => "target",
    };
}

my @queue = map { normalize_target_request($_) } @targets;
my @root_requests = @queue;
my %seen_req;
my %selected;
my %enabled;
my %target_by_sub;
my %config_by_root;
my %linkage_by_root;

while (@queue) {
    my $req = shift @queue;
    my $root = $req->{root};
    if (exists $override{$root} && $override{$root} ne $req->{requirement}) {
        add_audit("override", $root, "-", $override{$root}, "*", "selected", "override", "from=$req->{requirement};to=$override{$root}");
        $req->{requirement} = $override{$root};
    }
    my $sig = join("|", $req->{from}, $root, $req->{requirement}, $req->{subspecs}, $req->{source_pin}, $req->{checksum_required}, $req->{platform}, $req->{platform_version});
    next if $seen_req{$sig}++;
    my @eligible;
    for my $tk (keys %{ $tuples{$root} || {} }) {
        my $t = $tuples{$root}{$tk};
        my ($ok, $subs, $reason, $detail) = evaluate_tuple($t, $req);
        if (!$ok) {
            my $sub = @$subs ? join(",", @$subs) : "-";
            reject_tuple($t, $t->{version}, $sub, $reason, $detail);
            next;
        }
        push @eligible, { tuple => $t, subs => $subs, size => candidate_size($t, $subs) };
    }
    if (!@eligible) {
        $unsat{"no_eligible:$root"} = 1;
        next;
    }
    @eligible = sort { candidate_cmp($a, $b) } @eligible;
    my $winner = $eligible[0];
    my $old = $selected{$root};
    if (!$old || candidate_cmp($winner, { tuple => $old, size => candidate_size($old, $winner->{subs}) }) < 0) {
        $selected{$root} = $winner->{tuple};
    }
    my $current = $selected{$root};
    my $current_tk = tuple_key($current);
    my @subs = expand_subspecs($current, $req->{subspecs});
    my $to_subs = join(",", @subs);
    push @edges, [$req->{from}, "pod:$root/$to_subs\@$current->{version}", $req->{requirement}, $req->{reason}];
    for my $sub (@subs) {
        $enabled{$root}{$sub} = 1;
        $target_by_sub{$root}{$sub}{$req->{target}} = 1 if $req->{target};
        $config_by_root{$root}{$_} = 1 for list_values($req->{configurations}, ",");
        $linkage_by_root{$root}{$req->{linkage}} = 1 if $req->{linkage} ne "-";
    }
    for my $sub (@subs) {
        my $row = $spec{$current_tk}{$sub};
        next if !$row;
        for my $dep_cell (list_values($row->{dependencies}, ";")) {
            my $dep = parse_dep($dep_cell);
            my $dep_req = {
                target => $req->{target},
                direct => 0,
                from => "pod:$root/$sub\@$current->{version}",
                root => $dep->{root},
                requirement => $dep->{requirement},
                original_requirement => $dep->{requirement},
                subspecs => $dep->{subspecs},
                configurations => $req->{configurations},
                linkage => $req->{linkage},
                source_pin => $dep->{source_pin},
                checksum_required => $dep->{checksum_required},
                platform => $req->{platform},
                platform_version => $req->{platform_version},
                reason => "dependency",
            };
            push @queue, $dep_req;
        }
    }
}

@edges = ();
%enabled = ();
%target_by_sub = ();
%config_by_root = ();
%linkage_by_root = ();
my @rebuild_queue = @root_requests;
my %rebuilt_req;
while (@rebuild_queue) {
    my $req = shift @rebuild_queue;
    my $root = $req->{root};
    if (exists $override{$root} && $override{$root} ne $req->{requirement}) {
        $req = { %$req, requirement => $override{$root} };
    }
    next if !$selected{$root};
    my $t = $selected{$root};
    my $tk = tuple_key($t);
    my @subs = expand_subspecs($t, $req->{subspecs});
    my $sig = join("|", $req->{from}, $root, $t->{source}, $t->{version}, $req->{requirement}, join(",", @subs), $req->{target});
    next if $rebuilt_req{$sig}++;
    my $to_subs = join(",", @subs);
    push @edges, [$req->{from}, "pod:$root/$to_subs\@$t->{version}", $req->{requirement}, $req->{reason}];
    for my $sub (@subs) {
        $enabled{$root}{$sub} = 1;
        $target_by_sub{$root}{$sub}{$req->{target}} = 1 if $req->{target};
        $config_by_root{$root}{$_} = 1 for list_values($req->{configurations}, ",");
        $linkage_by_root{$root}{$req->{linkage}} = 1 if $req->{linkage} ne "-";
    }
    for my $sub (@subs) {
        my $row = $spec{$tk}{$sub};
        next if !$row;
        for my $dep_cell (list_values($row->{dependencies}, ";")) {
            my $dep = parse_dep($dep_cell);
            push @rebuild_queue, {
                target => $req->{target},
                direct => 0,
                from => "pod:$root/$sub\@$t->{version}",
                root => $dep->{root},
                requirement => $dep->{requirement},
                original_requirement => $dep->{requirement},
                subspecs => $dep->{subspecs},
                configurations => $req->{configurations},
                linkage => $req->{linkage},
                source_pin => $dep->{source_pin},
                checksum_required => $dep->{checksum_required},
                platform => $req->{platform},
                platform_version => $req->{platform_version},
                reason => "dependency",
            };
        }
    }
}

for my $root (keys %selected) {
    next if $enabled{$root};
    delete $selected{$root};
}

my %selected_audit_seen;
my $total_size = 0;
for my $root (sort keys %selected) {
    my $t = $selected{$root};
    my $tk = tuple_key($t);
    for my $sub (sort keys %{ $enabled{$root} || {} }) {
        my $row = $spec{$tk}{$sub};
        next if !$row;
        $total_size += int($row->{size});
        my $targets = join(",", sort keys %{ $target_by_sub{$root}{$sub} || {} });
        $targets = "dependency" if $targets eq "";
        my $sig = join("\t", $root, $t->{source}, $t->{version}, $sub);
        next if $selected_audit_seen{$sig}++;
        add_audit("selected", $root, $t->{source}, $t->{version}, $sub, "selected", "selected", $targets);
    }
}

my $rejected_count = scalar grep { $_->[0] eq "rejected" } @audit;
if ($total_size > int($policy{max_binary_size})) {
    $unsat{"no_valid_complete_plan"} = 1;
    add_audit("limit", "-", "-", "-", "-", "unsatisfied", "max_binary_size", "$total_size/$policy{max_binary_size}");
}
if ($rejected_count > int($policy{max_warnings})) {
    $unsat{"no_valid_complete_plan"} = 1;
    add_audit("limit", "-", "-", "-", "-", "unsatisfied", "max_warnings", "$rejected_count/$policy{max_warnings}");
}

remove_tree($OUT) if -d $OUT;
make_path($OUT);

sub pod_lock_lines {
    my @lines;
    push @lines, "PODS:";
    for my $root (sort keys %selected) {
        my $t = $selected{$root};
        my $tk = tuple_key($t);
        for my $sub (sort keys %{ $enabled{$root} || {} }) {
            push @lines, "  - $root/$sub ($t->{version})";
            my @deps;
            for my $dep_cell (list_values($spec{$tk}{$sub}{dependencies}, ";")) {
                my $dep = parse_dep($dep_cell);
                my $dep_subs = $dep->{subspecs};
                if ($dep_subs eq "-" && $selected{$dep->{root}}) {
                    $dep_subs = join(",", default_subspecs($selected{$dep->{root}}));
                }
                push @deps, "$dep->{root}/$dep_subs ($dep->{requirement})";
            }
            push @lines, map { "    - $_" } sort @deps;
        }
    }
    push @lines, "DEPENDENCIES:";
    for my $r (sort { "$a->{target}:$a->{pod}" cmp "$b->{target}:$b->{pod}" } @targets) {
        my $name = $r->{subspecs} eq "-" ? $r->{pod} : "$r->{pod}/$r->{subspecs}";
        push @lines, "  - $name ($r->{requirement}) [$r->{target};$r->{configurations};$r->{linkage}]";
    }
    push @lines, "SPEC REPOS:";
    for my $src (@source_order) {
        my @roots = sort grep { $selected{$_}{source} eq $src } keys %selected;
        next unless @roots;
        push @lines, "  $src:";
        push @lines, map { "    - $_" } @roots;
    }
    push @lines, "SPEC CHECKSUMS:";
    for my $root (sort keys %selected) {
        my $t = $selected{$root};
        my $tk = tuple_key($t);
        for my $sub (sort keys %{ $enabled{$root} || {} }) {
            push @lines, "  $root/$sub: $spec{$tk}{$sub}{checksum}";
        }
    }
    push @lines, "COCOAPODS: $policy{cocoapods_version}";
    my $status = keys(%unsat) ? "unsatisfied" : "ok";
    push @lines, "STATUS: $status";
    my $unsat = keys(%unsat) ? join(",", sort keys %unsat) : "-";
    push @lines, "UNSATISFIED: $unsat";
    return @lines;
}

open my $pl, ">", "$OUT/Podfile.lock" or die $!;
print {$pl} join("\n", pod_lock_lines()), "\n";
close $pl;

open my $pp, ">", "$OUT/pods-plan.tsv" or die $!;
print {$pp} "root\tsource\tversion\tsubspecs\tsize\ttargets\tconfigurations\tlinkage\tchecksums\n";
for my $root (sort keys %selected) {
    my $t = $selected{$root};
    my $tk = tuple_key($t);
    my @subs = sort keys %{ $enabled{$root} || {} };
    my $size = 0;
    my %checksums;
    my %targets;
    for my $sub (@subs) {
        $size += int($spec{$tk}{$sub}{size});
        $checksums{$spec{$tk}{$sub}{checksum}} = 1;
        $targets{$_} = 1 for keys %{ $target_by_sub{$root}{$sub} || {} };
    }
    print {$pp} join("\t",
        $root,
        $t->{source},
        $t->{version},
        @subs ? join(",", @subs) : "-",
        $size,
        keys(%targets) ? join(",", sort keys %targets) : "-",
        keys(%{ $config_by_root{$root} || {} }) ? join(",", sort keys %{ $config_by_root{$root} }) : "-",
        keys(%{ $linkage_by_root{$root} || {} }) ? join(",", sort keys %{ $linkage_by_root{$root} }) : "-",
        keys(%checksums) ? join(",", sort keys %checksums) : "-",
    ), "\n";
}
close $pp;

my %edge_seen;
my @edge_rows = sort { join("\t", @$a) cmp join("\t", @$b) } grep { !$edge_seen{join("\t", @$_)}++ } @edges;
open my $sg, ">", "$OUT/subspec-graph.tsv" or die $!;
print {$sg} "from\tto\trequirement\treason\n";
print {$sg} join("\t", @$_), "\n" for @edge_rows;
close $sg;

my %audit_seen;
my @audit_rows = sort { join("\t", @$a) cmp join("\t", @$b) } grep { !$audit_seen{join("\t", @$_)}++ } @audit;
open my $sa, ">", "$OUT/source-audit.tsv" or die $!;
print {$sa} "kind\troot\tsource\tversion\tsubspec\tstatus\treason\tdetail\n";
print {$sa} join("\t", @$_), "\n" for @audit_rows;
close $sa;

my $seal_input = "";
for my $f (qw(Podfile.lock pods-plan.tsv subspec-graph.tsv source-audit.tsv)) {
    open my $fh, "<", "$OUT/$f" or die $!;
    local $/;
    $seal_input .= <$fh>;
    close $fh;
}
open my $seal, ">", "$OUT/seal.txt" or die $!;
print {$seal} sha256_hex($seal_input), "\n";
close $seal;
PERL

chmod +x /opt/pod-lock-desk/pod-source-lock
/opt/pod-lock-desk/pod-source-lock
