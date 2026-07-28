#!/bin/bash
set -euo pipefail
cd /app

cat > /app/tools/compromise_reduce.pl <<'PERL'
#!/usr/bin/env perl
use strict;
use warnings;
use JSON::PP qw(decode_json);

my ($ledger, $snapshot, $incident, $date, $output) = @ARGV;
die "usage: compromise_reduce.pl LEDGER SNAPSHOT INCIDENT DATE OUTPUT\n" unless defined $output;
open my $lf, '<', $ledger or die "$ledger: $!\n";
my %latest;
while (my $line = <$lf>) {
    next if $line =~ /^\s*$/;
    my $row = decode_json($line);
    next unless ($row->{incident_id} // '') eq $incident;
    next unless ($row->{effective_on} // '') le $date;
    my $id = $row->{signer_id} // next;
    if (!exists $latest{$id} || $row->{effective_on} gt $latest{$id}{effective_on}) {
        $latest{$id} = $row;
    }
}
close $lf;
open my $sf, '<', $snapshot or die "$snapshot: $!\n";
my @ids;
while (my $line = <$sf>) {
    chomp $line;
    my ($id) = split /\t/, $line, 2;
    next if !defined($id) || $id eq 'signer_id' || $id eq '';
    push @ids, $id;
}
close $sf;
open my $out, '>', $output or die "$output: $!\n";
print {$out} "signer_id\tstate\teffective_on\treason\n";
for my $id (sort @ids) {
    my $row = $latest{$id};
    if (!$row) {
        print {$out} "$id\tclear\t\t\n";
    } elsif ($row->{cleared}) {
        print {$out} join("\t", $id, 'clear', $row->{effective_on}, $row->{reason} // ''), "\n";
    } else {
        print {$out} join("\t", $id, 'blocked', $row->{effective_on}, $row->{reason} // ''), "\n";
    }
}
close $out;
PERL
cat > /app/tools/delegation_verify.lua <<'LUA'
#!/usr/bin/env lua
local state_path, paths_path, incident, effective_date, max_hops, output_path = ...
if not output_path then
  io.stderr:write("usage: delegation_verify.lua STATE PATHS INCIDENT DATE MAX_HOPS OUTPUT\n")
  os.exit(2)
end
max_hops = tonumber(max_hops)
local roots, edges = {}, {}
for line in io.lines(state_path) do
  local fields = {}
  for field in (line .. "\t"):gmatch("(.-)\t") do table.insert(fields, field) end
  if fields[1] == "root" then
    roots[fields[2]] = fields[3]
  elseif fields[1] == "edge" then
    local key = fields[2] .. "\0" .. fields[3]
    edges[key] = {incident=fields[4], not_before=fields[5], not_after=fields[6], status=fields[7]}
  end
end
local input = assert(io.open(paths_path, "r"))
local output = assert(io.open(output_path, "w"))
output:write("signer_id\troot_id\tedge_count\tstatus\n")
local first = true
local invalid = false
for line in input:lines() do
  if first then first = false else
    local f = {}
    for field in (line .. "\t"):gmatch("(.-)\t") do table.insert(f, field) end
    local signer, root, hops, path = f[2], f[3], tonumber(f[4]), f[5]
    local nodes = {}
    for node in path:gmatch("[^>]+") do table.insert(nodes, node) end
    local ok = roots[root] == "trusted" and nodes[1] == root and nodes[#nodes] == signer
    ok = ok and hops == (#nodes - 1) and hops <= max_hops
    local seen = {}
    for _, node in ipairs(nodes) do
      if seen[node] then ok = false end
      seen[node] = true
    end
    for i = 1, #nodes - 1 do
      local edge = edges[nodes[i] .. "\0" .. nodes[i+1]]
      if not edge or edge.status ~= "active" or edge.incident ~= incident or
         edge.not_before > effective_date or edge.not_after < effective_date then
        ok = false
      end
    end
    output:write(string.format("%s\t%s\t%d\t%s\n", signer, root, #nodes - 1, ok and "valid" or "invalid"))
    if not ok then invalid = true end
  end
end
input:close(); output:close()
if invalid then os.exit(3) end
LUA
chmod 0755 /app/tools/compromise_reduce.pl /app/tools/delegation_verify.lua


request=/app/recovery/recovery-request.json
database=/app/data/features.db
ledger=/app/recovery/compromise-ledger.jsonl
snapshot=/app/recovery/candidate-snapshot.tsv
delegation_state=/app/recovery/delegation-state.tsv
policy=/app/trust/release-policy.json
model=/app/model/metadata.json
config=/app/config/screening.json

mkdir -p /app/trust/approvals /app/output
rm -f /app/trust/approvals/*.sig

incident=$(jq -er '.incident_id' "$request")
effective_date=$(jq -er '.effective_date' "$request")
minimum_sequence=$(jq -er '.minimum_release_sequence' "$request")
minimum_weight=$(jq -er '.minimum_assurance_weight' "$request")
minimum_regions=$(jq -er '.minimum_regions' "$request")
minimum_roots=$(jq -er '.minimum_delegation_roots' "$request")
minimum_security=$(jq -er '.minimum_security_signers' "$request")
maximum_risk=$(jq -er '.maximum_custody_risk' "$request")
maximum_hops=$(jq -er '.maximum_delegation_hops' "$request")
distinct_families=$(jq -er '.require_distinct_key_families' "$request")
distinct_custodians=$(jq -er '.require_distinct_custodians' "$request")
revoked_signer=$(jq -er '.revoked_signer' "$request")
roles_csv=$(jq -r '.required_roles | sort | join(",")' "$request")

/app/tools/compromise_reduce.pl "$ledger" "$snapshot" "$incident" "$effective_date" /app/output/compromise_decisions.tsv

eligible=/tmp/eligible.tsv
: > "$eligible"
while IFS=$'\t' read -r signer role row_inc sha status priority not_before not_after region family weight; do
    [ "$signer" = signer_id ] && continue
    [[ ",$roles_csv," == *",$role,"* ]] || continue
    [ "$row_inc" = "$incident" ] || continue
    [ "$status" = trusted ] || continue
    [[ "$not_before" < "$effective_date" || "$not_before" = "$effective_date" ]] || continue
    [[ "$not_after" > "$effective_date" || "$not_after" = "$effective_date" ]] || continue

    public="/app/recovery/candidates/${signer}-verification.material"
    [ -f "$public" ] || continue
    actual=$(sha256sum "$public" | awk '{print $1}')
    [ "$actual" = "$sha" ] || continue

    compromise_state=$(awk -F '\t' -v id="$signer" '$1==id {print $2}' /app/output/compromise_decisions.tsv)
    [ "$compromise_state" = clear ] || continue

    path_row=$(sqlite3 -separator $'\t' "$database" "
WITH RECURSIVE paths(root_id,node_id,path,hops) AS (
  SELECT root_id,root_id,root_id,0
  FROM trust_roots
  WHERE status='trusted'
  UNION ALL
  SELECT paths.root_id,
         edges.child_id,
         paths.path || '>' || edges.child_id,
         paths.hops + 1
  FROM paths
  JOIN delegation_edges AS edges ON edges.parent_id=paths.node_id
  WHERE edges.status='active'
    AND edges.incident_id='$incident'
    AND edges.not_before <= '$effective_date'
    AND edges.not_after >= '$effective_date'
    AND paths.hops < $maximum_hops
    AND instr('>' || paths.path || '>', '>' || edges.child_id || '>') = 0
)
SELECT root_id,path,hops
FROM paths
WHERE node_id='$signer'
ORDER BY hops,root_id,path
LIMIT 1;
")
    [ -n "$path_row" ] || continue
    IFS=$'\t' read -r root_id delegation_path delegation_hops <<< "$path_row"

    custody_row=$(sqlite3 -separator $'\t' "$database" \
        "SELECT custodian,risk_score FROM custody_controls WHERE signer_id='$signer';")
    [ -n "$custody_row" ] || continue
    IFS=$'\t' read -r custodian risk_score <<< "$custody_row"

    printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
        "$signer" "$role" "$priority" "$region" "$family" "$weight" "$sha" \
        "$root_id" "$delegation_path" "$delegation_hops" "$custodian" "$risk_score" \
        >> "$eligible"
done < "$snapshot"

sqlite3 -separator $'\t' "$database" "
SELECT signer_a,signer_b
FROM pair_denials
WHERE incident_id='$incident' AND active=1
ORDER BY signer_a,signer_b;
" > /tmp/pair_denials.tsv

selection=/tmp/selection.tsv
awk -F '\t' \
    -v roles="$roles_csv" \
    -v minw="$minimum_weight" \
    -v minr="$minimum_regions" \
    -v minroots="$minimum_roots" \
    -v minsec="$minimum_security" \
    -v maxrisk="$maximum_risk" \
    -v distinctfamilies="$distinct_families" \
    -v distinctcustodians="$distinct_custodians" '
function bitcount(x, count) {
    count=0
    while (x) {
        count += x % 2
        x = int(x / 2)
    }
    return count
}
function addset(set, value) {
    return index("," set ",", "," value ",") ? set : (set == "" ? value : set "," value)
}
function setcount(set, parts) {
    if (set == "") return 0
    return split(set, parts, ",")
}
function sorted_ids(mask, i, j, count, temp, result) {
    count=0
    for (i=1; i<=n; i++) {
        if (int(mask / 2^(i-1)) % 2) {
            count++
            ids[count]=signer[i]
        }
    }
    for (i=1; i<=count; i++) {
        for (j=i+1; j<=count; j++) {
            if (ids[j] < ids[i]) {
                temp=ids[i]
                ids[i]=ids[j]
                ids[j]=temp
            }
        }
    }
    result=ids[1]
    for (i=2; i<=count; i++) result=result "," ids[i]
    return result
}
FNR==NR {
    denied[$1 SUBSEP $2]=1
    denied[$2 SUBSEP $1]=1
    next
}
{
    n++
    signer[n]=$1
    role[n]=$2
    priority[n]=$3+0
    region[n]=$4
    family[n]=$5
    weight[n]=$6+0
    root[n]=$8
    custodian[n]=$11
    risk[n]=$12+0
    source[n]=$0
}
END {
    split(roles, required, ",")
    best=""
    for (mask=1; mask<2^n; mask++) {
        count=bitcount(mask)
        total_weight=0
        total_priority=0
        total_risk=0
        regions=""
        families=""
        roots=""
        custodians=""
        covered=""
        security_count=0
        invalid=0

        for (i=1; i<=n; i++) {
            if (!(int(mask / 2^(i-1)) % 2)) continue
            total_weight += weight[i]
            total_priority += priority[i]
            total_risk += risk[i]
            regions=addset(regions,region[i])
            families=addset(families,family[i])
            roots=addset(roots,root[i])
            custodians=addset(custodians,custodian[i])
            covered=addset(covered,role[i])
            if (role[i] == "security") security_count++
            for (j=i+1; j<=n; j++) {
                if (int(mask / 2^(j-1)) % 2 && denied[signer[i] SUBSEP signer[j]]) invalid=1
            }
        }

        for (i in required) {
            if (!index("," covered ",", "," required[i] ",")) invalid=1
        }
        if (total_weight < minw) invalid=1
        if (setcount(regions) < minr) invalid=1
        if (setcount(roots) < minroots) invalid=1
        if (security_count < minsec) invalid=1
        if (total_risk > maxrisk) invalid=1
        if (distinctfamilies == "true" && setcount(families) != count) invalid=1
        if (distinctcustodians == "true" && setcount(custodians) != count) invalid=1
        if (invalid) continue

        ids_string=sorted_ids(mask)
        score=sprintf("%04d|%09d|%09d|%s",count,total_priority,total_risk,ids_string)
        if (best == "" || score < best) {
            best=score
            bestmask=mask
        }
    }

    if (best == "") exit 2
    for (i=1; i<=n; i++) {
        if (int(bestmask / 2^(i-1)) % 2) print source[i]
    }
}' /tmp/pair_denials.tsv "$eligible" \
    | sort -t $'\t' -k2,2 -k1,1 > "$selection"

mapfile -t selected < <(cut -f1 "$selection" | sort)
primary=${selected[0]}
assurance_weight=$(awk -F '\t' '{sum+=$6} END{print sum+0}' "$selection")
total_priority=$(awk -F '\t' '{sum+=$3} END{print sum+0}' "$selection")
total_risk=$(awk -F '\t' '{sum+=$12} END{print sum+0}' "$selection")
mapfile -t regions < <(cut -f4 "$selection" | sort -u)
mapfile -t roots < <(cut -f8 "$selection" | sort -u)
signer_ids_json=$(printf '%s\n' "${selected[@]}" | jq -R . | jq -s .)
regions_json=$(printf '%s\n' "${regions[@]}" | jq -R . | jq -s .)
roots_json=$(printf '%s\n' "${roots[@]}" | jq -R . | jq -s .)

printf 'role\tsigner_id\tpriority\tregion\tkey_family\tassurance_weight\tpublic_key_sha256\n' \
    > /app/output/signer_quorum.tsv
awk -F '\t' 'BEGIN{OFS="\t"} {print $2,$1,$3,$4,$5,$6,$7}' "$selection" \
    >> /app/output/signer_quorum.tsv

printf 'role\tsigner_id\troot_id\thops\tdelegation_path\tcustodian\trisk_score\n' \
    > /app/output/delegation_paths.tsv
awk -F '\t' 'BEGIN{OFS="\t"} {print $2,$1,$8,$10,$9,$11,$12}' "$selection" \
    >> /app/output/delegation_paths.tsv
/app/tools/delegation_verify.lua \
    "$delegation_state" \
    /app/output/delegation_paths.tsv \
    "$incident" \
    "$effective_date" \
    "$maximum_hops" \
    /app/output/delegation_witnesses.tsv

compromise_decisions_sha=$(sha256sum /app/output/compromise_decisions.tsv | awk '{print $1}')
delegation_witnesses_sha=$(sha256sum /app/output/delegation_witnesses.tsv | awk '{print $1}')

latest_sequence=$(sqlite3 "$database" 'SELECT MAX(release_sequence) FROM release_history;')
latest_incident=$(sqlite3 "$database" \
    "SELECT incident_id FROM release_history WHERE release_sequence=$latest_sequence;")
if [ "$latest_incident" = "$incident" ]; then
    release_sequence=$latest_sequence
    previous_sequence=$(sqlite3 "$database" \
        "SELECT MAX(release_sequence) FROM release_history WHERE release_sequence < $latest_sequence;")
else
    previous_sequence=$latest_sequence
    release_sequence=$((latest_sequence + 1))
    [ "$release_sequence" -ge "$minimum_sequence" ] || release_sequence=$minimum_sequence
fi

previous_sha=$(sqlite3 "$database" \
    "SELECT policy_sha256 FROM release_history WHERE release_sequence=$previous_sequence;")
model_sha=$(sha256sum "$model" | awk '{print $1}')
snapshot_sha=$(sha256sum "$snapshot" | awk '{print $1}')
ledger_sha=$(sha256sum "$ledger" | awk '{print $1}')
delegation_sha=$(sha256sum "$delegation_state" | awk '{print $1}')
minimum_threshold=$(jq -er '.minimum_threshold' "$config")
maximum_threshold=$(jq -er '.maximum_threshold' "$config")

jq -nc \
    --arg kind logistic_regression \
    --argjson assurance_weight "$assurance_weight" \
    --arg snapshot "$snapshot_sha" \
    --arg ledger "$ledger_sha" \
    --arg compromise_decisions "$compromise_decisions_sha" \
    --arg delegation "$delegation_sha" \
    --arg delegation_witnesses "$delegation_witnesses_sha" \
    --arg incident "$incident" \
    --argjson maximum_threshold "$maximum_threshold" \
    --argjson minimum_threshold "$minimum_threshold" \
    --arg model "$model_sha" \
    --arg previous "$previous_sha" \
    --argjson regions "$regions_json" \
    --argjson release_sequence "$release_sequence" \
    --arg primary "$primary" \
    --argjson signer_ids "$signer_ids_json" \
    --argjson roots "$roots_json" \
    '{
      allowed_model_kind:$kind,
      assurance_weight:$assurance_weight,
      candidate_snapshot_sha256:$snapshot,
      compromise_decisions_sha256:$compromise_decisions,
      compromise_ledger_sha256:$ledger,
      delegation_state_sha256:$delegation,
      delegation_witnesses_sha256:$delegation_witnesses,
      incident_id:$incident,
      maximum_threshold:$maximum_threshold,
      minimum_threshold:$minimum_threshold,
      model_sha256:$model,
      previous_policy_sha256:$previous,
      regions:$regions,
      release_sequence:$release_sequence,
      signer_id:$primary,
      signer_ids:$signer_ids,
      trust_roots:$roots
    }' > "$policy"

cp "/app/recovery/candidates/${primary}-verification.material" /app/trust/release.pub
for signer in "${selected[@]}"; do
    output="/app/trust/approvals/${signer}.sig"
    [ "$signer" != "$primary" ] || output=/app/trust/release-policy.sig
    openssl dgst -sha256 \
        -sign "/app/recovery/candidates/${signer}-signing.material" \
        -out "$output" \
        "$policy"
done

policy_sha=$(sha256sum "$policy" | awk '{print $1}')
quorum=$(IFS=,; echo "${selected[*]}")
{
    echo 'BEGIN IMMEDIATE;'
    printf "UPDATE trusted_signers SET status='revoked' WHERE signer_id='%s';\n" \
        "$revoked_signer"
    while IFS=$'\t' read -r signer _ _ _ _ _ sha _; do
        printf "INSERT INTO trusted_signers(signer_id,public_key_sha256,status) VALUES('%s','%s','trusted') ON CONFLICT(signer_id) DO UPDATE SET public_key_sha256=excluded.public_key_sha256,status='trusted';\n" \
            "$signer" "$sha"
    done < "$selection"
    printf "INSERT INTO release_history(release_sequence,policy_sha256,incident_id,signer_quorum) VALUES(%s,'%s','%s','%s') ON CONFLICT(release_sequence) DO NOTHING;\n" \
        "$release_sequence" "$policy_sha" "$incident" "$quorum"
    echo 'COMMIT;'
} | sqlite3 "$database"

jq -nc \
    --argjson assurance_weight "$assurance_weight" \
    --argjson roots "$roots_json" \
    --argjson regions "$regions_json" \
    --argjson signer_count "${#selected[@]}" \
    --argjson signer_ids "$signer_ids_json" \
    --argjson total_priority "$total_priority" \
    --argjson total_risk "$total_risk" \
    '{
      assurance_weight:$assurance_weight,
      delegation_roots:$roots,
      regions:$regions,
      signer_count:$signer_count,
      signer_ids:$signer_ids,
      total_priority:$total_priority,
      total_risk:$total_risk
    }' > /app/output/quorum_summary.json

jq -nc \
    --arg snapshot "$snapshot_sha" \
    --arg ledger "$ledger_sha" \
    --arg compromise_decisions "$compromise_decisions_sha" \
    --arg delegation "$delegation_sha" \
    --arg delegation_witnesses "$delegation_witnesses_sha" \
    --arg incident "$incident" \
    --arg policy "$policy_sha" \
    --arg previous "$previous_sha" \
    --argjson release_sequence "$release_sequence" \
    --argjson signature_count "${#selected[@]}" \
    --argjson signer_ids "$signer_ids_json" \
    '{
      candidate_snapshot_sha256:$snapshot,
      compromise_decisions_sha256:$compromise_decisions,
      compromise_ledger_sha256:$ledger,
      delegation_state_sha256:$delegation,
      delegation_witnesses_sha256:$delegation_witnesses,
      incident_id:$incident,
      policy_sha256:$policy,
      previous_policy_sha256:$previous,
      release_sequence:$release_sequence,
      signature_count:$signature_count,
      signer_ids:$signer_ids
    }' > /app/output/recovery_audit.json

/app/bin/screening-gate --output /app/output/gate.json
