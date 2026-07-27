# Sample Analysis Run

The sequence below walks one country record from ingestion through every
statistical operation the engine supports.

## Initialize the database
```
/app/wb-tracker init
# Output: OK
```

## Fetch a country by ISO code
```
/app/wb-tracker fetch-country US
# Output: ok country=US name=United States

/app/wb-tracker fetch-country us
# Output: exists  (case-insensitive, already stored)

/app/wb-tracker fetch-country ZZ
# stderr: not_found: ZZ  (exit 1)
```

## List all stored countries
```
/app/wb-tracker list-countries
# Output (tab-separated):
# BR  Brazil  LCN  UMC  Brasilia
# DE  Germany ECS  HIC  Berlin
# US  United States NAC HIC Washington D.C.
```

## View aggregate statistics
```
/app/wb-tracker country-stats
# count=3
# avg_latitude=21.000000
# stddev_latitude=24.123456
# p75_latitude=38.500000
# p90_latitude=51.000000
```

## Verify the audit chain
```
/app/wb-tracker audit-verify
# ok chain_length=3
```
