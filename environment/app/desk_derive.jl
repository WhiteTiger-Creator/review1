# Broken lab helper: uses arithmetic mean / first string / round — not desk-derivation.md
using Printf

const POLICY_KEY_ORDER = [
    "schema_version", "phase_tol_rad", "gain_tol_db", "freq_match_eps_hz",
    "freq_anchor", "c_mps", "steer_az_deg", "steer_el_deg", "el_law", "norm_mode",
    "ref_antenna_id", "wrap_half_open", "wrap_compose", "phase_sign", "geo_sign",
    "amp_law", "mutual_alpha", "neighbor_radius_m", "mutual_kernel", "couple_mask",
    "taper_beta", "taper_origin", "ref_phase_align", "align_mode",
    "outlier_mode", "cluster_metric", "cluster_phase_scale", "cluster_gain_scale",
    "rms_basis", "digest_bind", "policy_revision",
]

const INT_KEYS = Set([
    "schema_version", "wrap_half_open", "phase_sign", "geo_sign", "ref_phase_align",
])

const STR_KEYS = Set([
    "freq_anchor", "el_law", "norm_mode", "ref_antenna_id", "wrap_compose", "amp_law",
    "mutual_kernel", "couple_mask", "taper_origin", "align_mode", "outlier_mode",
    "cluster_metric", "rms_basis", "digest_bind", "policy_revision",
])

function write_derived_policy(journal_path::String, out_path::String)
    kept = Dict{String,Vector{String}}()
    open(journal_path, "r") do io
        first = true
        for raw in eachline(io)
            line = replace(raw, "\r" => "")
            s = strip(line)
            isempty(s) && continue
            startswith(s, "#") && continue
            if first
                first = false
                continue
            end
            parts = split(line, ',')
            length(parts) == 3 || continue
            field = strip(parts[1])
            vote = strip(parts[2])
            token = strip(parts[3])
            vote == "yes" || continue
            push!(get!(kept, field, String[]), token)
        end
    end
    open(out_path, "w") do io
        for key in POLICY_KEY_ORDER
            toks = get(kept, key, String[])
            isempty(toks) && error("missing $key")
            if key in INT_KEYS
                vals = [parse(Int, t) for t in toks]
                v = Int(round(sum(vals) / length(vals)))
                println(io, "$key = $v")
            elseif key in STR_KEYS
                println(io, "$key = \"$(toks[1])\"")
            else
                vals = [parse(Float64, t) for t in toks]
                v = sum(vals) / length(vals)
                println(io, "$key = $(@sprintf("%.10f", v))")
            end
        end
    end
end
