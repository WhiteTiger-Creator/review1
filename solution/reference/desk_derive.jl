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

function _median_f(vals::Vector{Float64})::Float64
    s = sort(vals)
    n = length(s)
    if n % 2 == 1
        return s[(n ÷ 2) + 1]
    end
    return 0.5 * (s[n ÷ 2] + s[(n ÷ 2) + 1])
end

function _midmean_f(vals::Vector{Float64})::Float64
    n = length(vals)
    n < 3 && return _median_f(vals)
    s = sort(vals)
    return sum(@view s[2:(n - 1)]) / (n - 2)
end

function _fmt_float(x::Float64)::String
    if abs(x - round(x)) < 1e-12 && abs(x) < 1e15
        return @sprintf("%.1f", round(x))
    end
    s = @sprintf("%.10f", x)
    s = rstrip(s, '0')
    endswith(s, '.') && (s *= "0")
    return s
end

function load_journal(path::String)::Dict{String,Vector{String}}
    kept = Dict{String,Vector{String}}()
    open(path, "r") do io
        first = true
        for raw in eachline(io)
            line = replace(raw, "\r" => "")
            s = strip(line)
            isempty(s) && continue
            startswith(s, "#") && continue
            if first
                first = false
                hdr = [strip(p) for p in split(line, ',')]
                hdr == ["field", "vote", "token"] || error("bad journal header")
                continue
            end
            parts = split(line, ',')
            length(parts) == 3 || error("bad journal arity")
            field = strip(parts[1])
            vote = strip(parts[2])
            token = strip(parts[3])
            vote in ("yes", "no") || error("bad vote")
            vote == "yes" || continue
            field in POLICY_KEY_ORDER || error("unknown field $field")
            push!(get!(kept, field, String[]), token)
        end
    end
    return kept
end

function derive_policy_map(journal_path::String)::Dict{String,Any}
    kept = load_journal(journal_path)
    out = Dict{String,Any}()
    for key in POLICY_KEY_ORDER
        haskey(kept, key) || error("missing field $key")
        toks = kept[key]
        isempty(toks) && error("empty field $key")
        if key in INT_KEYS
            vals = [parse(Int, t) for t in toks]
            m = sum(vals) / length(vals)
            out[key] = Int(ceil(m - 1e-15))
        elseif key in STR_KEYS
            best = toks[1]
            for t in toks
                if length(t) < length(best) || (length(t) == length(best) && t < best)
                    best = t
                end
            end
            out[key] = best
        else
            vals = [parse(Float64, t) for t in toks]
            out[key] = _midmean_f(vals)
        end
    end
    out["schema_version"] == 8 || error("schema not 8")
    return out
end

function write_derived_policy(journal_path::String, out_path::String)
    pol = derive_policy_map(journal_path)
    parent = dirname(out_path)
    !isempty(parent) && mkpath(parent)
    open(out_path, "w") do io
        for key in POLICY_KEY_ORDER
            v = pol[key]
            if key in STR_KEYS
                println(io, "$key = \"$v\"")
            elseif key in INT_KEYS
                println(io, "$key = $v")
            else
                println(io, "$key = $(_fmt_float(Float64(v)))")
            end
        end
    end
end
