struct AntennaRow
    antenna_id::String
    x_m::Float64
    y_m::Float64
    freq_hz::Float64
    phase_meas_rad::Float64
    gain_err_db::Float64
    ref_phase_rad::Float64
end

const EXPECTED_HEADER = ["antenna_id", "x_m", "y_m", "freq_hz", "phase_meas_rad", "gain_err_db", "ref_phase_rad"]

function load_array_csv(path::String)::Vector{AntennaRow}
    rows = AntennaRow[]
    seen = Dict{String,Bool}()
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
                length(hdr) == 7 || error("bad header arity")
                hdr == EXPECTED_HEADER || error("bad header")
                continue
            end
            parts = split(line, ',')
            length(parts) == 7 || error("bad arity")
            id = strip(parts[1])
            isempty(id) && error("empty id")
            haskey(seen, id) && error("duplicate id")
            seen[id] = true
            x = parse(Float64, strip(parts[2]))
            y = parse(Float64, strip(parts[3]))
            f = parse(Float64, strip(parts[4]))
            pm = parse(Float64, strip(parts[5]))
            ge = parse(Float64, strip(parts[6]))
            rp = parse(Float64, strip(parts[7]))
            if !isfinite(x) || !isfinite(y) || !isfinite(f) || !isfinite(pm) || !isfinite(ge) || !isfinite(rp)
                error("non-finite")
            end
            f > 0.0 || error("nonpositive freq")
            push!(rows, AntennaRow(id, x, y, f, pm, ge, rp))
        end
    end
    isempty(rows) && error("empty array")
    return rows
end

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

function _hinge_f(vals::Vector{Float64})::Float64
    n = length(vals)
    n < 4 && return _median_f(vals)
    s = sort(vals)
    lo = s[Int(floor((n - 1) / 4)) + 1]
    hi = s[Int(ceil(3 * (n - 1) / 4)) + 1]
    return 0.5 * (lo + hi)
end

function validate_frequency_spread(rows::Vector{AntennaRow}, policy::CalPolicy)
    freqs = [r.freq_hz for r in rows]
    fstar = if policy.freq_anchor == "first"
        freqs[1]
    elseif policy.freq_anchor == "median"
        _median_f(freqs)
    elseif policy.freq_anchor == "midmean"
        _midmean_f(freqs)
    else
        _hinge_f(freqs)
    end
    for r in rows
        abs(r.freq_hz - fstar) > policy.freq_match_eps_hz && error("freq spread")
    end
end

function require_ref_antenna(rows::Vector{AntennaRow}, ref_id::String)
    count(r -> r.antenna_id == ref_id, rows) == 1 || error("ref antenna")
end
