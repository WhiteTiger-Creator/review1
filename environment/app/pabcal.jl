include("/app/src/policy_load.jl")
include("/app/src/csv_load.jl")
include("/app/src/compensate.jl")
include("/app/src/weights.jl")
include("/app/src/report_emit.jl")

function parse_args(args::Vector{String})
    # legacy flag names still wired here
    defaults = Dict(
        "array" => "/app/data/sample_array.csv",
        "config" => "/app/config/cal_policy.toml",
        "cal" => "/app/corrected_cal.csv",
        "summary" => "/app/cal_summary.json",
    )
    seen = Dict{String,Bool}()
    i = 1
    while i <= length(args)
        a = args[i]
        startswith(a, "--") || error("bad flag")
        key = a[3:end]
        key in keys(defaults) || error("unknown flag")
        haskey(seen, key) && error("dup flag")
        i == length(args) && error("missing value")
        defaults[key] = args[i + 1]
        seen[key] = true
        i += 2
    end
    paths = [defaults["array"], defaults["config"], defaults["cal"], defaults["summary"]]
    length(unique(paths)) == 4 || error("path collision")
    return defaults
end

function main()
    local opts
    try
        opts = parse_args(ARGS)
    catch e
        println(stderr, sprint(showerror, e))
        exit(2)
    end
    try
        policy = load_policy(opts["config"])
        rows = load_array_csv(opts["array"])
        validate_frequency_spread(rows, policy)
        require_ref_antenna(rows, policy.ref_antenna_id)
        elems = build_elements(rows, policy)
        rms = rms_phase(elems, policy)
        maxg = max_gain_dev(elems)
        extra = cluster_extra_count(elems)
        digest = cal_digest(elems, rms, maxg, policy)
        write_cal_csv(opts["cal"], elems)
        write_summary_json(opts["summary"], policy, elems, rms, maxg, digest, extra)
        outliers = count(e -> e.exceeds_tol, elems)
        exit(outliers == 0 ? 0 : 1)
    catch e
        println(stderr, sprint(showerror, e))
        exit(2)
    end
end

main()
