function wrap_phase(x::Float64, wrap_half_open::Int)::Float64
    twoπ = 2.0 * π
    y = x
    if wrap_half_open == 1
        while y > π
            y -= twoπ
        end
        while y <= -π
            y += twoπ
        end
    else
        while y >= π
            y -= twoπ
        end
        while y < -π
            y += twoπ
        end
    end
    return y
end

function amp_from_gain_db(gain_err_db::Float64, amp_law::String)::Float64
    if amp_law == "power"
        return 10.0^(-gain_err_db / 10.0)
    end
    return 10.0^(-gain_err_db / 20.0)
end

function geometric_phase(x_m::Float64, y_m::Float64, freq_hz::Float64, policy::CalPolicy)::Float64
    k = 2.0 * π * freq_hz / policy.c_mps
    az = policy.steer_az_deg * π / 180.0
    el = policy.steer_el_deg * π / 180.0
    el_factor = policy.el_law == "cos_el" ? cos(el) : 1.0
    raw = -k * (x_m * sin(az) * el_factor + y_m * sin(el))
    return Float64(policy.geo_sign) * raw
end

function coupling_factor(
    idx::Int,
    rows::Vector{AntennaRow},
    deltas::Vector{Float64},
    policy::CalPolicy,
)::Float64
    xi = rows[idx].x_m
    yi = rows[idx].y_m
    s = 0.0
    R = policy.neighbor_radius_m
    for j in eachindex(rows)
        j == idx && continue
        if policy.couple_mask == "gain_inliers"
            abs(rows[j].gain_err_db) > policy.gain_tol_db && continue
        elseif policy.couple_mask == "dual_inliers"
            (abs(rows[j].gain_err_db) > policy.gain_tol_db || abs(deltas[j]) > policy.phase_tol_rad) && continue
        end
        d = hypot(xi - rows[j].x_m, yi - rows[j].y_m)
        if d <= R
            u = d / R
            if policy.mutual_kernel == "quadratic"
                s += u * u
            elseif policy.mutual_kernel == "gaussian"
                s += 1.0 - exp(-u * u)
            else
                s += u
            end
        end
    end
    return exp(-policy.mutual_alpha * s)
end

function taper_origin_xy(rows::Vector{AntennaRow}, policy::CalPolicy)::Tuple{Float64,Float64}
    if policy.taper_origin == "ref"
        ref = findfirst(r -> r.antenna_id == policy.ref_antenna_id, rows)
        ref === nothing && error("ref missing")
        return (rows[ref].x_m, rows[ref].y_m)
    end
    n = length(rows)
    cx = sum(r -> r.x_m, rows) / n
    cy = sum(r -> r.y_m, rows) / n
    return (cx, cy)
end

function spatial_taper(x_m::Float64, y_m::Float64, ox::Float64, oy::Float64, policy::CalPolicy)::Float64
    R = policy.neighbor_radius_m
    rho = hypot(x_m - ox, y_m - oy) / R
    return exp(-policy.taper_beta * rho * rho)
end

function compose_weight_phase(delta::Float64, geo::Float64, policy::CalPolicy)::Float64
    resid = Float64(policy.phase_sign) * delta
    if policy.wrap_compose == "wrap_each_then_sum"
        return wrap_phase(resid, policy.wrap_half_open) + wrap_phase(geo, policy.wrap_half_open)
    end
    return wrap_phase(resid + geo, policy.wrap_half_open)
end
