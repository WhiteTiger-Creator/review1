struct CalElement
    antenna_id::String
    x_m::Float64
    y_m::Float64
    freq_hz::Float64
    delta_phase_rad::Float64
    amp_linear::Float64
    couple::Float64
    taper::Float64
    steer_phase_rad::Float64
    w_real::Float64
    w_imag::Float64
    exceeds_tol::Bool
    gain_err_db::Float64
    primary_outlier::Bool
end

function align_ref_phase!(elems::Vector{CalElement}, policy::CalPolicy)
    policy.ref_phase_align == 1 || return
    ref_i = findfirst(e -> e.antenna_id == policy.ref_antenna_id, elems)
    ref_i === nothing && error("ref missing in elems")
    wr = elems[ref_i].w_real
    wi = elems[ref_i].w_imag
    if policy.align_mode == "div_ref"
        mag = hypot(wr, wi)
        mag == 0.0 && return
        denom = wr * wr + wi * wi
        for i in eachindex(elems)
            e = elems[i]
            nr = (e.w_real * wr + e.w_imag * wi) / denom
            ni = (e.w_imag * wr - e.w_real * wi) / denom
            elems[i] = CalElement(
                e.antenna_id, e.x_m, e.y_m, e.freq_hz, e.delta_phase_rad, e.amp_linear, e.couple, e.taper,
                e.steer_phase_rad, nr, ni, e.exceeds_tol, e.gain_err_db, e.primary_outlier,
            )
        end
    else
        θ = atan(wi, wr)
        c = cos(-θ)
        s = sin(-θ)
        for i in eachindex(elems)
            e = elems[i]
            nr = e.w_real * c - e.w_imag * s
            ni = e.w_real * s + e.w_imag * c
            elems[i] = CalElement(
                e.antenna_id, e.x_m, e.y_m, e.freq_hz, e.delta_phase_rad, e.amp_linear, e.couple, e.taper,
                e.steer_phase_rad, nr, ni, e.exceeds_tol, e.gain_err_db, e.primary_outlier,
            )
        end
    end
end

function normalize_weights!(elems::Vector{CalElement}, mode::String)
    mode == "none" && return
    mags = [hypot(e.w_real, e.w_imag) for e in elems]
    if mode == "unit_peak"
        denom = maximum(mags)
    elseif mode == "unit_l2"
        denom = sqrt(sum(m -> m * m, mags))
    else
        error("bad norm")
    end
    denom == 0.0 && return
    for i in eachindex(elems)
        e = elems[i]
        elems[i] = CalElement(
            e.antenna_id, e.x_m, e.y_m, e.freq_hz, e.delta_phase_rad, e.amp_linear, e.couple, e.taper,
            e.steer_phase_rad, e.w_real / denom, e.w_imag / denom, e.exceeds_tol, e.gain_err_db, e.primary_outlier,
        )
    end
end

function _cluster_near(xp::Float64, yp::Float64, xq::Float64, yq::Float64, R::Float64, metric::String)::Bool
    dx = abs(xp - xq)
    dy = abs(yp - yq)
    if metric == "chebyshev"
        return max(dx, dy) <= R
    end
    return hypot(dx, dy) <= R
end

function mark_outliers!(elems::Vector{CalElement}, policy::CalPolicy)
    for i in eachindex(elems)
        e = elems[i]
        primary = abs(e.delta_phase_rad) > policy.phase_tol_rad || abs(e.gain_err_db) > policy.gain_tol_db
        elems[i] = CalElement(
            e.antenna_id, e.x_m, e.y_m, e.freq_hz, e.delta_phase_rad, e.amp_linear, e.couple, e.taper,
            e.steer_phase_rad, e.w_real, e.w_imag, primary, e.gain_err_db, primary,
        )
    end
    policy.outlier_mode == "union_then_cluster" || return
    pthresh = policy.phase_tol_rad * policy.cluster_phase_scale
    gthresh = policy.gain_tol_db * policy.cluster_gain_scale
    primary_idx = [i for i in eachindex(elems) if elems[i].primary_outlier]
    marked = falses(length(elems))
    for i in eachindex(elems)
        marked[i] = elems[i].exceeds_tol
    end
    for p in primary_idx
        xp = elems[p].x_m
        yp = elems[p].y_m
        for q in eachindex(elems)
            q == p && continue
            if _cluster_near(xp, yp, elems[q].x_m, elems[q].y_m, policy.neighbor_radius_m, policy.cluster_metric) &&
               abs(elems[q].delta_phase_rad) > pthresh &&
               abs(elems[q].gain_err_db) > gthresh
                marked[q] = true
            end
        end
    end
    for i in eachindex(elems)
        e = elems[i]
        elems[i] = CalElement(
            e.antenna_id, e.x_m, e.y_m, e.freq_hz, e.delta_phase_rad, e.amp_linear, e.couple, e.taper,
            e.steer_phase_rad, e.w_real, e.w_imag, marked[i], e.gain_err_db, e.primary_outlier,
        )
    end
end

function rms_phase(elems::Vector{CalElement}, policy::CalPolicy)::Float64
    if policy.rms_basis == "inliers"
        vals = [e.delta_phase_rad for e in elems if !e.exceeds_tol]
        isempty(vals) && return 0.0
        return sqrt(sum(v -> v * v, vals) / length(vals))
    end
    vals = [e.delta_phase_rad for e in elems]
    return sqrt(sum(v -> v * v, vals) / length(vals))
end

function max_gain_dev(elems::Vector{CalElement})::Float64
    return maximum(e -> abs(e.gain_err_db), elems)
end

function cluster_extra_count(elems::Vector{CalElement})::Int
    return count(e -> e.exceeds_tol && !e.primary_outlier, elems)
end

function build_elements(rows::Vector{AntennaRow}, policy::CalPolicy)::Vector{CalElement}
    deltas = [wrap_phase(r.phase_meas_rad - r.ref_phase_rad, policy.wrap_half_open) for r in rows]
    elems = CalElement[]
    ox, oy = taper_origin_xy(rows, policy)
    for (i, r) in enumerate(rows)
        delta = deltas[i]
        amp = amp_from_gain_db(r.gain_err_db, policy.amp_law)
        couple = coupling_factor(i, rows, deltas, policy)
        taper = spatial_taper(r.x_m, r.y_m, ox, oy, policy)
        amp_eff = amp * couple * taper
        geo = geometric_phase(r.x_m, r.y_m, r.freq_hz, policy)
        phi_w = compose_weight_phase(delta, geo, policy)
        wr = amp_eff * cos(phi_w)
        wi = amp_eff * sin(phi_w)
        push!(elems, CalElement(
            r.antenna_id, r.x_m, r.y_m, r.freq_hz, delta, amp, couple, taper, phi_w, wr, wi, false, r.gain_err_db, false,
        ))
    end
    align_ref_phase!(elems, policy)
    normalize_weights!(elems, policy.norm_mode)
    mark_outliers!(elems, policy)
    sort!(elems, by = e -> e.antenna_id)
    return elems
end
