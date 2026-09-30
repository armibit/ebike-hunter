# Configuration

Configuration lives in two files:

- `config/config.yaml`: buyer profile, filters, scoring, portals.
- `config/taxonomy.json`: spec detection patterns.

Secrets stay in `.env` (see [Setup](setup.md)).

## `config.yaml`

### `app`

| Key | Default | Meaning |
|-----|---------|---------|
| `log_level` | `INFO` | Console log level (files always get DEBUG) |
| `parallel_scans` | `5` | Portals scanned concurrently |
| `availability_checks_per_run` | `300` | Max "is it sold?" checks per scan |

### `buyer_profile`

```yaml
buyer_profile:
  location:            # distances are measured from here
    name: "Lugano, Ticino"
    latitude: 46.0037
    longitude: 8.9511
  max_radius_km:
    italy: 150         # Italian private listings beyond this are rejected
    exempt_portals: [...]  # shops that ship: never rejected for distance
  budget:
    target_price: 2200
    hard_max_price: 3000        # above: rejected
    full_score_price: 1800      # at or below: full price score
    suspicious_min_price: 900   # below: rejected as a likely scam
  rider_specs:
    target_sizes: [M, S2, S3, ...]  # other frame sizes are rejected
```

All of Switzerland is always accepted; distance only lowers the score.

Locations are resolved at province or canton level (`src/pipeline/geo_data.py`) from:

- an Italian province code ("Merone (CO)");
- a Swiss postcode ("9524 Zuzwil");
- a canton or province name.

Distances are indicative (±20 km).

### `hardware_requirements`

```yaml
hardware_requirements:
  category: "full_suspension"      # hardtails are rejected
  travel_front_range: [130, 160]   # scored in the fit component
  travel_rear_range: [130, 160]
  min_motor_torque_nm: 60          # below: rejected
  min_battery_wh: 500              # below: rejected
```

### `scoring_weights`

```yaml
scoring_weights:
  price_value: 0.35
  component_quality: 0.25
  condition_mileage: 0.15
  location_proximity: 0.15
  fit_geometry: 0.10
```

### `portals`

There is one block per portal, each with `enabled: true|false` plus portal-specific search settings. For example, Subito takes the paths exactly as they appear in its URLs:

```yaml
portals:
  subito_it:
    enabled: true
    search_paths:
      - "/annunci-lombardia/vendita/biciclette"
      - "/annunci-piemonte/vendita/biciclette/verbano-cusio-ossola"
```

## Scoring formula

The score (0–100) is the weighted sum of five sub-scores (`src/pipeline/scoring.py`):

| Component | Weight | Based on |
|-----------|--------|----------|
| Price value | 35 % | Full score up to `full_score_price`, exponential decay to `hard_max_price` |
| Component quality | 25 % | Motor tier/torque, battery Wh, brakes, fork. An unverified motor guess scores lower |
| Condition / mileage | 15 % | Odometer km |
| Location proximity | 15 % | Haversine distance from `buyer_profile.location` |
| Fit / geometry | 10 % | Frame size and suspension travel |

## `taxonomy.json`

This file holds the regex patterns for motors, brakes, forks and frame sizes. After editing it, apply the changes to stored listings with `python3 scripts/reprocess_all.py`.

To test a title quickly:

```bash
python3 -c "import sys; sys.path.insert(0,'src'); from pipeline.regex_parser import RegexParser; print(RegexParser('config/taxonomy.json').parse('Turbo Levo M Bosch CX 625Wh', 'fully'))"
```
