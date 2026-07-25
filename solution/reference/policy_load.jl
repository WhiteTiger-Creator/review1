struct CalPolicy
    schema_version::Int
    phase_tol_rad::Float64
    gain_tol_db::Float64
    freq_match_eps_hz::Float64
    freq_anchor::String
    c_mps::Float64
    steer_az_deg::Float64
    steer_el_deg::Float64
    el_law::String
    norm_mode::String
    ref_antenna_id::String
    wrap_half_open::Int
    wrap_compose::String
    phase_sign::Int
    geo_sign::Int
    amp_law::String
    mutual_alpha::Float64
    neighbor_radius_m::Float64
    mutual_kernel::String
    couple_mask::String
    taper_beta::Float64
    taper_origin::String
    ref_phase_align::Int
    align_mode::String
    outlier_mode::String
    cluster_metric::String
    cluster_phase_scale::Float64
    cluster_gain_scale::Float64
    rms_basis::String
    digest_bind::String
    policy_revision::String
end

function _parse_toml_scalars(path::String)::Dict{String,String}
    d = Dict{String,String}()
    open(path, "r") do io
        for raw in eachline(io)
            line = replace(raw, "\r" => "")
            s = strip(line)
            isempty(s) && continue
            startswith(s, "#") && continue
            occursin('=', s) || error("bad toml line")
            k, v = split(s, '=', limit=2)
            key = strip(k)
            val = strip(v)
            if startswith(val, "\"") && endswith(val, "\"") && length(val) >= 2
                val = val[2:end-1]
            end
            haskey(d, key) && error("dup key")
            d[key] = val
        end
    end
    return d
end

function load_policy(path::String)::CalPolicy
    d = _parse_toml_scalars(path)
    required = [
        "schema_version", "phase_tol_rad", "gain_tol_db", "freq_match_eps_hz",
        "freq_anchor", "c_mps", "steer_az_deg", "steer_el_deg", "el_law", "norm_mode",
        "ref_antenna_id", "wrap_half_open", "wrap_compose", "phase_sign", "geo_sign",
        "amp_law", "mutual_alpha", "neighbor_radius_m", "mutual_kernel", "couple_mask",
        "taper_beta", "taper_origin", "ref_phase_align", "align_mode",
        "outlier_mode", "cluster_metric", "cluster_phase_scale", "cluster_gain_scale",
        "rms_basis", "digest_bind", "policy_revision",
    ]
    for k in required
        haskey(d, k) || error("missing key $k")
    end
    for k in keys(d)
        k in required || error("unknown key $k")
    end
    schema = parse(Int, d["schema_version"])
    schema == 8 || error("bad schema")
    phase_tol = parse(Float64, d["phase_tol_rad"])
    gain_tol = parse(Float64, d["gain_tol_db"])
    freq_eps = parse(Float64, d["freq_match_eps_hz"])
    fanch = d["freq_anchor"]
    fanch in ("first", "median", "midmean", "hinge") || error("bad freq_anchor")
    c = parse(Float64, d["c_mps"])
    az = parse(Float64, d["steer_az_deg"])
    el = parse(Float64, d["steer_el_deg"])
    elaw = d["el_law"]
    elaw in ("flat", "cos_el") || error("bad el_law")
    mode = d["norm_mode"]
    mode in ("none", "unit_peak", "unit_l2") || error("bad norm_mode")
    ref = d["ref_antenna_id"]
    isempty(ref) && error("empty ref")
    wrap = parse(Int, d["wrap_half_open"])
    wrap in (0, 1) || error("bad wrap")
    wcomp = d["wrap_compose"]
    wcomp in ("sum_then_wrap", "wrap_each_then_sum") || error("bad wrap_compose")
    sign = parse(Int, d["phase_sign"])
    sign in (-1, 1) || error("bad phase_sign")
    gsign = parse(Int, d["geo_sign"])
    gsign in (-1, 1) || error("bad geo_sign")
    alaw = d["amp_law"]
    alaw in ("voltage", "power") || error("bad amp_law")
    alpha = parse(Float64, d["mutual_alpha"])
    alpha >= 0.0 || error("bad mutual_alpha")
    radius = parse(Float64, d["neighbor_radius_m"])
    radius > 0.0 || error("bad radius")
    kernel = d["mutual_kernel"]
    kernel in ("linear", "quadratic", "gaussian") || error("bad mutual_kernel")
    cmask = d["couple_mask"]
    cmask in ("all", "gain_inliers", "dual_inliers") || error("bad couple_mask")
    taper = parse(Float64, d["taper_beta"])
    taper >= 0.0 || error("bad taper_beta")
    torig = d["taper_origin"]
    torig in ("centroid", "ref") || error("bad taper_origin")
    align = parse(Int, d["ref_phase_align"])
    align in (0, 1) || error("bad align")
    amode = d["align_mode"]
    amode in ("arg_zero", "div_ref") || error("bad align_mode")
    omode = d["outlier_mode"]
    omode in ("union", "union_then_cluster") || error("bad outlier_mode")
    cmetric = d["cluster_metric"]
    cmetric in ("euclid", "chebyshev") || error("bad cluster_metric")
    cscale = parse(Float64, d["cluster_phase_scale"])
    cscale > 0.0 || error("bad cluster phase scale")
    gscale = parse(Float64, d["cluster_gain_scale"])
    gscale > 0.0 || error("bad cluster gain scale")
    rbasis = d["rms_basis"]
    rbasis in ("all", "inliers") || error("bad rms_basis")
    dbind = d["digest_bind"]
    dbind in ("weights", "couple_weights", "taper_couple_weights", "schema_taper_couple_w") || error("bad digest_bind")
    rev = d["policy_revision"]
    isempty(rev) && error("empty revision")
    (phase_tol > 0.0 && gain_tol > 0.0 && freq_eps > 0.0 && c > 0.0) || error("nonpositive policy")
    isfinite(az) && isfinite(el) || error("nonfinite steer")
    return CalPolicy(
        schema, phase_tol, gain_tol, freq_eps, fanch, c, az, el, elaw, mode, ref, wrap, wcomp,
        sign, gsign, alaw, alpha, radius, kernel, cmask, taper, torig, align, amode, omode,
        cmetric, cscale, gscale, rbasis, dbind, rev,
    )
end
