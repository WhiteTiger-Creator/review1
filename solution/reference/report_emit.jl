using Printf
using SHA

function _fmt10(x::Float64)::String
    y = ifelse(x == 0.0, 0.0, x)
    return @sprintf("%.10f", y)
end

function _fmt6(x::Float64)::String
    y = ifelse(x == 0.0, 0.0, x)
    return @sprintf("%.6f", y)
end

function cal_digest(elems::Vector{CalElement}, rms::Float64, maxg::Float64, policy::CalPolicy)::String
    parts = String["rev:$(policy.policy_revision)"]
    if policy.digest_bind == "schema_taper_couple_w"
        push!(parts, "schema:$(policy.schema_version)")
    end
    for e in elems
        if policy.digest_bind == "weights"
            push!(parts, "$(e.antenna_id):$(_fmt10(e.w_real)):$(_fmt10(e.w_imag))")
        elseif policy.digest_bind == "couple_weights"
            push!(parts, "$(e.antenna_id):$(_fmt10(e.couple)):$(_fmt10(e.w_real)):$(_fmt10(e.w_imag))")
        else
            push!(parts, "$(e.antenna_id):$(_fmt10(e.taper)):$(_fmt10(e.couple)):$(_fmt10(e.w_real)):$(_fmt10(e.w_imag))")
        end
    end
    push!(parts, "rms:$(_fmt10(rms)):maxg:$(_fmt10(maxg))")
    blob = join(parts, "\n")
    return bytes2hex(sha256(Vector{UInt8}(codeunits(blob))))
end

function write_cal_csv(path::String, elems::Vector{CalElement})
    parent = dirname(path)
    !isempty(parent) && mkpath(parent)
    tmp = path * ".tmp"
    open(tmp, "w") do io
        println(io, "antenna_id,x_m,y_m,freq_hz,delta_phase_rad,amp_linear,couple,taper,steer_phase_rad,w_real,w_imag,exceeds_tol")
        for e in elems
            println(io, join([
                e.antenna_id,
                _fmt10(e.x_m),
                _fmt10(e.y_m),
                _fmt6(e.freq_hz),
                _fmt10(e.delta_phase_rad),
                _fmt10(e.amp_linear),
                _fmt10(e.couple),
                _fmt10(e.taper),
                _fmt10(e.steer_phase_rad),
                _fmt10(e.w_real),
                _fmt10(e.w_imag),
                e.exceeds_tol ? "true" : "false",
            ], ","))
        end
    end
    mv(tmp, path; force=true)
end

function write_summary_json(
    path::String,
    policy::CalPolicy,
    elems::Vector{CalElement},
    rms::Float64,
    maxg::Float64,
    digest::String,
    extra::Int,
)
    parent = dirname(path)
    !isempty(parent) && mkpath(parent)
    tmp = path * ".tmp"
    outliers = [e.antenna_id for e in elems if e.exceeds_tol]
    open(tmp, "w") do io
        print(io, "{")
        print(io, "\"schema_version\":$(policy.schema_version),")
        print(io, "\"policy_revision\":\"$(policy.policy_revision)\",")
        print(io, "\"antenna_count\":$(length(elems)),")
        print(io, "\"outlier_count\":$(length(outliers)),")
        print(io, "\"cluster_extra_count\":$extra,")
        print(io, "\"rms_phase_err_rad\":$rms,")
        print(io, "\"max_gain_dev_db\":$maxg,")
        print(io, "\"outlier_ids\":[")
        for (i, id) in enumerate(outliers)
            i > 1 && print(io, ",")
            print(io, "\"$id\"")
        end
        print(io, "],")
        print(io, "\"cal_digest\":\"$digest\",")
        print(io, "\"steer_az_deg\":$(policy.steer_az_deg),")
        print(io, "\"steer_el_deg\":$(policy.steer_el_deg),")
        print(io, "\"norm_mode\":\"$(policy.norm_mode)\",")
        print(io, "\"ref_antenna_id\":\"$(policy.ref_antenna_id)\",")
        print(io, "\"ref_phase_align\":$(policy.ref_phase_align),")
        print(io, "\"amp_law\":\"$(policy.amp_law)\",")
        print(io, "\"wrap_compose\":\"$(policy.wrap_compose)\"")
        println(io, "}")
    end
    mv(tmp, path; force=true)
end
