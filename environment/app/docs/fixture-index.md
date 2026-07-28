# Fixture index

Public campaigns under `/app/fixtures/campaigns/`:

| Campaign id | Notes |
|-------------|-------|
| `NACA0012-A4` | Four-degree incidence, symmetric paired taps |
| `RAE2822-A2` | Cambered station set, tighter closure tol |
| `FLATPLATE-A0` | Near-zero alpha sanity campaign |

Held-out verifier campaigns are supplied only at grading time under tests/verifier-fixtures and are not shipped in the agent image. Synthesized held-out campaigns use campaign_id values HELD-ALPHA and HELD-BETA with perturbed angle of attack and scaled pressure coefficients; closure and seal rules are identical to public campaigns.
