"""
stages.py
=========
Infrastructure stage specifications for the SBB MehrSpur Zürich–Winterthur project.

A 'stage' captures the physical infrastructure and operational interventions
that modify the multimodal transport network and skims in the Canton Zürich FSM model.

HOW TO USE
----------
Edit the two named packages below to define physical interventions and their
spatial scope. Each package groups railway improvements, mobility hubs and
appraisal assumptions (CAPEX, construction emissions and asset lifetime).
Baseline headway, technology and capacity assumptions stay in parameters.py;
deployment timing and triggers stay in adaptive_planning.py.
ASCs/betas describe common behavior, not automatic benefits of individual hubs.
Asset lifetimes below affect final-year appraisal only, not transport.

SURROGATE CONSEQUENCE
---------------------
The two packages can operate independently. Transport states are 0 (baseline),
1 (stations), 2 (tunnel), and 3 (both). The combined state contains the two
packages' benefits once each plus COMBINED_EFFECTS. One GP learns all four configurations. Changes
to their physical effects require rebuilding the surrogate and response table.
Changing only plan timing, costs, comfort capacity, construction emissions or
asset lifetimes does not require a surrogate rebuild. Rerun appraisal to include them.

--- CHEAT SHEET: PARAMETERS & INTERVENTIONS ---

1. Defining Spatial Scopes
   Interventions are targeted geographically using spatial filters:
   
   - "area_pairs": Selects OD skim cells between origins and destinations, not physical links.
     Filter by "municipality_name" (e.g. "Dietikon") or "city_quartier" (e.g. "Altstetten").
     Example: Reducing rail travel time between Zürich and Winterthur:
       "railway_expansions": [
           {
               "name": "Corridor Rail Upgrade",
               "area_pairs": [
                   {"origin": {"municipality_name": "Zürich"}, "destination": {"municipality_name": "Winterthur"}}
               ],
               "both_directions": True,
               "effects": {
                   "travel_time_reduction_pct": 15.0
               }
           }
       ]
   
   - "zones": Used for area-wide or zone-based interventions (e.g., station access, local networks).
     Filter by specific zone IDs or whole municipality names. The model selects
     the first two candidate stops per zone for walk and bicycle access, then
     applies effects to journeys using those stops.
     Example: Improving PT access & egress times in Dietlikon:
       "mobility_hubs": [
           {
               "name": "Dietlikon Hub Area",
               "zones": [{"municipality_name": "Dietlikon"}],  # or zone IDs: ["15401012"]
               "effects": {
                   "access_time_reduction_pct": 20.0,
                   "egress_time_reduction_pct": 20.0
               }
           }
       ]


2. Mode-Specific Physical Interventions
   Effects are defined under specific mode keys which target different transport networks:
   - "railway_expansions": A list of railway interventions. The section/service
     entry sets minutes saved, headway reduction and added comfort capacity.
     Additional entries can use OD filters and percentage "effects" as above.
   - "bike_highways": Modifies the Bicycle network.
   - "road_capacity": Modifies selected directed links in the local MSA road network.
   - "mobility_hubs": Modifies PT access, egress and transfer times for walk and bicycle access.
   - "section_time_saving_min" in a "railway_expansions" entry, or directly in a
     package: Minutes saved on the selected parameters.SECTION. For bike_route,
     enter the saving for the complete route; each journey receives the fraction
     corresponding to the improved route length it uses. A pt_stop instead uses
     station-specific mobility_hubs effects below.
     Savings are relative to baseline: stations save 1 minute, the tunnel 4,
     and both packages 6, including a 1-minute combined bonus. The optional external cohort receives the same saving
     in appraisal, without entering mode choice or assignment.
     Section settings follow parameters.SECTION; headway settings apply between
     corridor municipalities. OD filters on additional entries scope only their
     percentage "effects". Comfort capacity is used in crowding appraisal.

   Within these keys, you can apply effects like:
   - "travel_time_reduction_pct" (Reduces in-vehicle travel time)
   - "speed_increase_pct" (Increases average speed)
   - "distance_reduction_pct" (Reduces trip distance, e.g., a new tunnel or bridge)
   - "access_time_reduction_pct", "egress_time_reduction_pct" (Reduces walk time to/from PT)
   
   EXAMPLE 1: Road intervention (increasing selected link capacity by 25%)
   "road_capacity": [
       {
           # Find these directional IDs with the link editor in Notebook 02.
           "edge_ids": ["OSM_123456_789012_0", "OSM_789012_123456_0"],
           "effects": {"capacity_increase_pct": 25.0}
       }
   ]

   Road capacity is link-based: ``area_pairs`` select OD skim cells and cannot
   identify physical road links. The transport interface applies these edits
   to a copy of the corridor immediately before MSA assignment.

   EXAMPLE 2: Station Access Intervention (Reducing PT access/egress times by 20%)
   "mobility_hubs": [
       {
           "zones": [{"municipality_name": "Dietlikon"}],
           "effects": {"access_time_reduction_pct": 20.0, "egress_time_reduction_pct": 20.0}
       }
   ]

   EXAMPLE 3: Bike Intervention (Shortening bike travel distance by 15% via a direct cycle path/bridge)
   "bike_highways": [
       {
           "area_pairs": [{"origin": {"city_quartier": "Altstetten"}, "destination": {"municipality_name": "Dietikon"}}],
           "both_directions": True,
           "effects": {
               "distance_reduction_pct": 15.0,
               "speed_increase_pct": 10.0
           }
       }
   ]

   For a counted cycling route configured in parameters.SECTION, a package can
   instead set "section_time_saving_min": 2.0 directly. Do not also apply an OD
   time reduction for the same improvement.

   EXAMPLE 4: A specific station (rather than a municipality-wide access package)
   "mobility_hubs": [
       {"station": "Wallisellen", "effects": {
           "access_time_reduction_pct": 25.0,
           "egress_time_reduction_pct": 20.0,
           "transfer_time_reduction_pct": 15.0
       }}
   ]
   Access and egress affect their respective station users. Transfer reductions
   affect only represented physical walking at this station, not through users.
"""

from __future__ import annotations
from copy import deepcopy
import itertools
from math import isfinite

# =============================================================================
# 1. PACKAGES: RAILWAY IMPROVEMENTS, MOBILITY HUBS AND APPRAISAL
# =============================================================================
# =============================================================================
# Feingliedrige FSM-Zonen-IDs des Limmattal-Korridors
# =============================================================================
CORRIDOR_ZONES = [
    13101001, 13101005, 13101010, 13501002, 16101002, 16101004, 16101006, 16101007,
    19101001, 19101002, 19101003, 19101004, 19101005, 19301001, 19501001, 24301001,
    24301002, 24301003, 24301004, 24301005, 24301006, 24301007, 24301008, 24301009,
    24301010, 24301011, 24301012, 24301013, 24301014, 24301015, 24301016, 24301017,
    24301018, 24301019, 24301020, 24301021, 24301022, 24301023, 24301024, 24301025,
    24301026, 24301027, 24401005, 24501001, 24501002, 24501003, 24501004, 24601001,
    24701001, 24701002, 24701003, 24701004, 24701005, 24701006, 24701007, 24701008,
    24701009, 24701010, 24701011, 24701012, 24701013, 24701014, 24701015, 24701016,
    24701017, 24701018, 24701019, 24701020, 24801002, 24801003, 24901001, 24901002,
    24901003, 25001001, 25001002, 25001003, 25001004, 25001005, 25001006, 25001007,
    25001008, 25001009, 25101001, 25101003, 26101001, 26101002, 26101003, 26101004,
    26101005, 26101006, 26101007, 26101008, 26101009, 26101010, 26101011, 26101012,
    26101013, 26101014, 26101015, 26101016, 26101017, 26101018, 26101019, 26101020,
    26101021, 26101022, 26101023, 26101024, 26101025, 26101026, 26101027, 26101028,
    26101029, 26101030, 26101031, 26101032, 26101033, 26101034, 26101035, 26101036,
    26101037, 26101038, 26101039, 26101040, 26101041, 26101042, 26101043, 26101044,
    26101045, 26101046, 26101047, 26101048, 26101049, 26101050, 26101051, 26101052,
    26101053, 26101054, 26101055, 26101056, 26101057, 26101058, 26101059, 26101060,
    26101061, 26101062, 26101063, 26101064, 26101065, 26101066, 26101067, 26101068,
    26101069, 26101070, 26101071, 26101072, 26101073, 26101074, 26101075, 26101076,
    26101077, 26101078, 26101079, 26101080, 26101081, 26101082, 26101083, 26101084,
    26101085, 26101086, 26101087, 26101088, 26101089, 26101090, 26101091, 26101092,
    26101093, 26101094, 26101095, 26101096, 26101097, 26101098, 26101099, 26101200,
    26101201, 26101202, 26101203, 26101204, 26101205, 26103306, 26103307, 26103308,
    6601001, 6601002, 6601003, 6601006, 6601008, 6601009, 6901001, 6901002,
    6901004, 6901007, 6901008, 6901011, 6901015, 6902019, 9601012, 9601014, 9701004,
]

CORRIDOR_AREA_PAIRS = [
    {"origin": {"grid_id": str(z1)}, "destination": {"grid_id": str(z2)}}
    for z1 in CORRIDOR_ZONES for z2 in CORRIDOR_ZONES if z1 != z2
]

# -----------------------------------------------------------------------------
# Specific Underpass Area Pairs (einzeln editierbar im UI)
# -----------------------------------------------------------------------------

# 3 grosse Unterführungen (Stage 1)
MAJOR_UNDERPASS_1 = [{"origin": {"grid_id": "24301018"}, "destination": {"grid_id": "24301022"}}]
MAJOR_UNDERPASS_2 = [{"origin": {"grid_id": "24301022"}, "destination": {"grid_id": "25101001"}}]
MAJOR_UNDERPASS_3 = [{"origin": {"grid_id": "24701009"}, "destination": {"grid_id": "24701013"}}]

# 5 kleine Unterführungen (Stage 2)
MINOR_UNDERPASS_1 = [{"origin": {"grid_id": "24301014"}, "destination": {"grid_id": "24301005"}}]
MINOR_UNDERPASS_2 = [{"origin": {"grid_id": "24301005"}, "destination": {"grid_id": "24301018"}}]
MINOR_UNDERPASS_3 = [{"origin": {"grid_id": "24301018"}, "destination": {"grid_id": "24301016"}}]
MINOR_UNDERPASS_4 = [{"origin": {"grid_id": "24701010"}, "destination": {"grid_id": "24701016"}}]
MINOR_UNDERPASS_5 = [{"origin": {"grid_id": "24701017"}, "destination": {"grid_id": "24701020"}}]

# =============================================================================
# PACKAGES DEFINITION
# =============================================================================
PACKAGES = {
    "stations": {
        "name": "Stage 1 – Bike Highway Roll-out + 3 Major Underpasses",
        "bike_highways": [
            {
                "name": "Bike Highway Limmattal Corridor (Main Axis)",
                "area_pairs": CORRIDOR_AREA_PAIRS,
                "both_directions": True,
                "effects": {
                    "travel_time_reduction_pct": 12.0,
                    "speed_increase_pct": 10.0,
                    "distance_reduction_pct": 5.0,
                },
            },
            {
                "name": "Major Underpass 1 (24301018 ↔ 24301022)",
                "area_pairs": MAJOR_UNDERPASS_1,
                "both_directions": True,
                "effects": {
                    "travel_time_reduction_pct": 20.0,
                    "speed_increase_pct": 15.0,
                    "distance_reduction_pct": 10.0,
                },
            },
            {
                "name": "Major Underpass 2 (24301022 ↔ 25101001)",
                "area_pairs": MAJOR_UNDERPASS_2,
                "both_directions": True,
                "effects": {
                    "travel_time_reduction_pct": 20.0,
                    "speed_increase_pct": 15.0,
                    "distance_reduction_pct": 10.0,
                },
            },
            {
                "name": "Major Underpass 3 (24701009 ↔ 24701013)",
                "area_pairs": MAJOR_UNDERPASS_3,
                "both_directions": True,
                "effects": {
                    "travel_time_reduction_pct": 20.0,
                    "speed_increase_pct": 15.0,
                    "distance_reduction_pct": 10.0,
                },
            },
        ],
        "appraisal": {
            "capital_cost_chf": 28_422_872,
            "lifetime_years": 40,
            "capital_share": 0.80,
            "construction_co2_tonnes": 2_500.0,
        },
    },
    "tunnel": {
        "name": "Stage 2 – 5 Additional Minor Underpasses",
        "bike_highways": [
            {
                "name": "Minor Underpass 1 (24301014 ↔ 24301005)",
                "area_pairs": MINOR_UNDERPASS_1,
                "both_directions": True,
                "effects": {"travel_time_reduction_pct": 15.0, "speed_increase_pct": 10.0},
            },
            {
                "name": "Minor Underpass 2 (24301005 ↔ 24301018)",
                "area_pairs": MINOR_UNDERPASS_2,
                "both_directions": True,
                "effects": {"travel_time_reduction_pct": 15.0, "speed_increase_pct": 10.0},
            },
            {
                "name": "Minor Underpass 3 (24301018 ↔ 24301016)",
                "area_pairs": MINOR_UNDERPASS_3,
                "both_directions": True,
                "effects": {"travel_time_reduction_pct": 15.0, "speed_increase_pct": 10.0},
            },
            {
                "name": "Minor Underpass 4 (24701010 ↔ 24701016)",
                "area_pairs": MINOR_UNDERPASS_4,
                "both_directions": True,
                "effects": {"travel_time_reduction_pct": 15.0, "speed_increase_pct": 10.0},
            },
            {
                "name": "Minor Underpass 5 (24701017 ↔ 24701020)",
                "area_pairs": MINOR_UNDERPASS_5,
                "both_directions": True,
                "effects": {"travel_time_reduction_pct": 15.0, "speed_increase_pct": 10.0},
            },
        ],
        "appraisal": {
            "capital_cost_chf": 2_688_120,
            "lifetime_years": 40,
            "capital_share": 0.80,
            "construction_co2_tonnes": 500.0,
        },
    },
}

# Synergie-Bonus, wenn Stage 1 + Stage 2 gemeinsam gebaut werden
COMBINED_EFFECTS = {
    "name": "Both stages – Complete Bike Highway & All 8 Underpasses",
    "bike_highways": [
        {
            "name": "Corridor Synergy (Continuous Grade-Separated Route)",
            "area_pairs": CORRIDOR_AREA_PAIRS,
            "both_directions": True,
            "effects": {
                "travel_time_reduction_pct": 4.0,
                "speed_increase_pct": 3.0,
            },
        }
    ],
}


# =============================================================================
# INTERNAL ASSEMBLY AND APPRAISAL HELPERS (normally leave unchanged)
# =============================================================================
STATE_IDS = (0, 1, 2, 3)
STATE_LABELS = {0: "Baseline", 1: "Stations only", 2: "Tunnel only", 3: "Stations + tunnel"}
STATE_COLORS = {0: "#9E9E9E", 1: "#FFC107", 2: "#2196F3", 3: "#4CAF50"}
_STATE_COMPONENTS = {0: (False, False), 1: (True, False), 2: (False, True), 3: (True, True)}


def _railway_entries(package: dict) -> list[dict]:
    """Use the same list (or single dictionary) form as native interventions."""
    entries = package.get("railway_expansions") or []
    if isinstance(entries, dict):
        entries = [entries]
    if not isinstance(entries, list) or any(not isinstance(entry, dict) for entry in entries):
        raise ValueError("railway_expansions must be a list of intervention dictionaries.")
    return entries


def _package_railway_effect(package: dict, key: str) -> float:
    """Sum an additive section/service assumption across railway entries."""
    total = 0.0
    entries = _railway_entries(package)
    if key == "section_time_saving_min":
        entries = [package, *entries]
    for entry in entries:
        try:
            value = float(entry.get(key, 0.0))
        except (TypeError, ValueError) as error:
            raise ValueError(f"{key} must be a finite nonnegative number.") from error
        if not isfinite(value) or value < 0:
            raise ValueError(f"{key} must be a finite nonnegative number.")
        total += value
    return total


def _railway_od_interventions(package: dict) -> list[dict]:
    """Keep OD interventions after extracting section/service assumptions."""
    settings = {"section_time_saving_min", "headway_reduction_min", "capacity_increase"}
    interventions = []
    for entry in _railway_entries(package):
        intervention = {key: deepcopy(value) for key, value in entry.items() if key not in settings}
        if intervention.keys() - {"name", "description"}:
            interventions.append(intervention)
    return interventions


def package_parameter_defaults() -> dict:
    """Expose package inputs under the shared appraisal/uncertainty parameter keys."""
    values = {}
    for number, name in enumerate(("stations", "tunnel"), 1):
        package = PACKAGES[name]
        values[f"C_INV_STAGE{number}"] = package["appraisal"]["capital_cost_chf"]
        values[f"CAPACITY_INCREASE_STAGE{number}"] = _package_railway_effect(package, "capacity_increase")
    values["CAPACITY_INCREASE_COMBINED"] = _package_railway_effect(COMBINED_EFFECTS, "capacity_increase")
    return values


def package_appraisal_settings() -> dict:
    """Appraisal cache inputs, read from the single package configuration."""
    return {
        "asset_lifetimes": {
            name: {key: package["appraisal"][key] for key in ("lifetime_years", "capital_share")}
            for name, package in PACKAGES.items()
        },
        "construction_emissions": {
            name: package["appraisal"]["construction_co2_tonnes"]
            for name, package in PACKAGES.items()
            if "construction_co2_tonnes" in package["appraisal"]
        },
    }


def get_stages(params: dict | None = None, *, packages: dict | None = None,
               combined_effects: dict | None = None) -> dict[int, dict]:
    """Assemble baseline (0), stations (1), tunnel (2), and both packages (3).

    Each package's physical effects are included once, with combined-only
    effects added to state 3. Appraisal settings stay outside the transport
    specifications. A third independently scheduled package needs model changes.
    Optional package arguments support notebook exploration without changing
    the saved PACKAGES or COMBINED_EFFECTS definitions.
    """
    import parameters as p
    params = {**p.NOMINAL_PARAMS, **(params or {})}

    # Waiting effects cover different corridor municipalities in both directions.
    # Section in-vehicle savings instead follow parameters.SECTION route coverage.
    service_od_pairs = [
        {"origin": {"municipality_name": o}, "destination": {"municipality_name": d}}
        for o, d in itertools.combinations(p.CORRIDOR_MUNICIPALITIES, 2)
    ]
    return _assemble_stages(
        PACKAGES if packages is None else packages, params, service_od_pairs,
        combined_effects=combined_effects,
    )


def stage_components(stage: int) -> tuple[bool, bool]:
    """Return whether the station and tunnel packages are operating."""
    return _STATE_COMPONENTS[int(stage)]


def state_for_components(stations_active: bool, tunnel_active: bool) -> int:
    """Select a transport state from two independently operating packages."""
    components = (bool(stations_active), bool(tunnel_active))
    return next(state for state, active in _STATE_COMPONENTS.items() if active == components)


def stage_headway(stage: int, params: dict | None = None) -> float:
    """Minutes between services after additive package and combined-only savings."""
    import parameters as p
    params = {**p.NOMINAL_PARAMS, **(params or {})}
    headway = float(params["PT_HEADWAY_BASELINE"])
    if not isfinite(headway) or headway <= 0:
        raise ValueError("PT_HEADWAY_BASELINE must be finite and positive.")
    reduction = _stage_minute_effect(stage, "headway_reduction_min")
    if reduction >= headway:
        raise ValueError("Total headway reduction must be smaller than PT_HEADWAY_BASELINE.")
    return headway - reduction


def _stage_minute_effect(stage: int, key: str) -> float:
    """Sum configured package minutes, adding the bonus only when both operate."""
    active_packages = stage_components(stage)
    packages = [PACKAGES[name]
                for name, active in zip(("stations", "tunnel"), active_packages) if active]
    if all(active_packages):
        packages.append(COMBINED_EFFECTS)
    return sum(_package_railway_effect(package, key) for package in packages)


def stage_capacity(stage: int, params: dict | None = None) -> float:
    """Peak-hour comfort threshold with package increases and a combined-only bonus."""
    import parameters as p
    params = {**p.NOMINAL_PARAMS, **(params or {})}
    baseline = float(params["PT_CAPACITY_BASELINE"])
    if not isfinite(baseline) or baseline <= 0:
        raise ValueError("PT_CAPACITY_BASELINE must be finite and positive.")
    increase = 0.0
    for package, active in enumerate(stage_components(stage), 1):
        value = float(params[f"CAPACITY_INCREASE_STAGE{package}"])
        if not isfinite(value) or value < 0:
            raise ValueError("Capacity increases must be finite nonnegative fractions.")
        if active:
            increase += value
    bonus = float(params["CAPACITY_INCREASE_COMBINED"])
    if not isfinite(bonus) or bonus < 0:
        raise ValueError("Combined capacity increase must be a finite nonnegative fraction.")
    if all(stage_components(stage)):
        increase += bonus
    return baseline * (1.0 + increase)


def _service_wait_effects(stage: int, params: dict) -> dict:
    """Convert the final state headway to one initial/transfer waiting reduction."""
    reduction = 100.0 * (1.0 - stage_headway(stage, params) / stage_headway(0, params))
    return {"initial_wait_reduction_pct": reduction, "transfer_wait_reduction_pct": reduction}


def _assemble_stages(packages: dict, params: dict, service_od_pairs: list[dict], *,
                     combined_effects: dict | None = None) -> dict[int, dict]:
    """Expand concise inputs to the existing native schema and combine packages."""
    combined_effects = COMBINED_EFFECTS if combined_effects is None else combined_effects

    def minute_effect(stage: int, key: str) -> float:
        active = stage_components(stage)
        selected = [packages[name] for name, enabled in zip(("stations", "tunnel"), active) if enabled]
        if all(active):
            selected.append(combined_effects)
        return sum(_package_railway_effect(package, key) for package in selected)

    technology = {
        "ebike_share": float(params["EBIKE_SHARE"]),
        "EBIKE_SPEED_MULTIPLIER": float(params["EBIKE_SPEED_MULTIPLIER"]),
    }
    # Native intervention defaults, not additional student assumptions.
    effect_defaults = {
        "railway_expansions": dict.fromkeys((
            "travel_time_reduction_pct", "speed_increase_pct", "distance_reduction_pct",
            "initial_wait_reduction_pct", "transfer_wait_reduction_pct",
            "transfer_time_reduction_pct", "access_time_reduction_pct", "egress_time_reduction_pct",
        ), 0.0),
        "mobility_hubs": dict.fromkeys((
            "access_time_reduction_pct", "transfer_time_reduction_pct",
            "initial_wait_reduction_pct", "transfer_wait_reduction_pct", "egress_time_reduction_pct",
        ), 0.0),
    }
    stages = {0: {"name": "Stage 0 – Baseline Network", "section_time_saving_min": 0.0, **technology}}
    for stage, package in ((1, "stations"), (2, "tunnel")):
        inputs = deepcopy(packages[package])
        inputs.pop("appraisal", None)
        inputs.pop("section_time_saving_min", None)
        inputs.pop("railway_expansions", None)
        for key in ("mobility_hubs", "bike_highways", "road_capacity"):
            if isinstance(inputs.get(key), dict):
                inputs[key] = [inputs[key]]
        railway_od = _railway_od_interventions(packages[package])
        if railway_od:
            inputs["railway_expansions"] = railway_od
        specification = {
            "name": inputs.pop("name"),
            "section_time_saving_min": minute_effect(stage, "section_time_saving_min"),
            **technology, **inputs,
        }
        stages[stage] = specification
    combined = deepcopy(stages[2])
    combined["name"] = "Both stages - Tunnel and Hubs"
    combined["section_time_saving_min"] = minute_effect(3, "section_time_saving_min")
    for key in ("railway_expansions", "mobility_hubs", "bike_highways", "road_capacity"):
        if key in stages[1] or key in stages[2] or key in combined_effects:
            bonus = (_railway_od_interventions(combined_effects) if key == "railway_expansions"
                     else combined_effects.get(key, []))
            if isinstance(bonus, dict):
                bonus = [bonus]
            combined[key] = deepcopy(stages[1].get(key, []) + stages[2].get(key, []) + bonus)
    stages[3] = combined
    for stage, specification in stages.items():
        if stage:
            headway = float(params["PT_HEADWAY_BASELINE"])
            reduction = minute_effect(stage, "headway_reduction_min")
            if not isfinite(headway) or headway <= 0 or reduction >= headway:
                raise ValueError("Total headway reduction must be smaller than a positive PT_HEADWAY_BASELINE.")
            wait_effect = 100.0 * (1.0 - (headway - reduction) / headway)
            # One final service-frequency intervention avoids compounding the
            # packages' percentages when their minute savings are additive.
            specification.setdefault("railway_expansions", []).append({
                "name": "Corridor service frequency",
                "area_pairs": deepcopy(service_od_pairs),
                "both_directions": True,
                "effects": {"initial_wait_reduction_pct": wait_effect,
                            "transfer_wait_reduction_pct": wait_effect},
            })
        for key, defaults in effect_defaults.items():
            for intervention in specification.get(key, []):
                intervention["effects"] = {**defaults, **intervention.get("effects", {})}
    return stages


def construction_emissions_tonnes(package: int | str) -> float:
    """Total construction tonnes CO2e for package 1/stations or 2/tunnel."""
    package_names = {1: "stations", 2: "tunnel", "stations": "stations", "tunnel": "tunnel"}
    if isinstance(package, bool) or package not in package_names:
        raise ValueError("Construction emissions package must be 1/'stations' or 2/'tunnel'.")
    try:
        value = float(PACKAGES[package_names[package]]["appraisal"].get("construction_co2_tonnes", 0.0))
    except (TypeError, ValueError) as error:
        raise ValueError("Construction emissions must be finite nonnegative tonnes CO2e.") from error
    if not isfinite(value) or value < 0:
        raise ValueError("Construction emissions must be finite nonnegative tonnes CO2e.")
    return value


def asset_residual_value(package: int | str, investment_chf: float, operated_years: float) -> float:
    """Undiscounted CHF remaining at horizon end for one built package.

    Package IDs 1 and 2 mean stations and tunnel, respectively. Transport state 3
    combines both packages, so value each package separately. Named packages
    "stations" and "tunnel" are accepted too. The caller supplies actual capital
    paid, omits unbuilt packages, and discounts the credit in the final year.
    """
    package_names = {1: "stations", 2: "tunnel", "stations": "stations", "tunnel": "tunnel"}
    if isinstance(package, bool) or package not in package_names:
        raise ValueError("Residual valuation package must be 1/'stations' or 2/'tunnel'.")
    settings = PACKAGES[package_names[package]]["appraisal"]
    try:
        investment = float(investment_chf)
        age = float(operated_years)
        share = float(settings["capital_share"])
    except (TypeError, ValueError) as exc:
        raise ValueError("Asset investment_chf, operated_years and capital_share must be numeric.") from exc
    if not isfinite(investment) or investment < 0:
        raise ValueError("Asset investment_chf must be finite and nonnegative.")
    if not isfinite(age) or age < 0:
        raise ValueError("Asset operated_years must be finite and nonnegative.")
    if not isfinite(share) or not 0 <= share <= 1:
        raise ValueError("Asset capital_share must be a finite fraction between zero and one.")
    if share == 0:
        return 0.0
    try:
        lifetime = float(settings["lifetime_years"])
    except (TypeError, ValueError) as exc:
        raise ValueError("An enabled asset lifetime_years must be finite and positive.") from exc
    if not isfinite(lifetime) or lifetime <= 0:
        raise ValueError("An enabled asset lifetime_years must be finite and positive.")
    return investment * share * max(0.0, 1.0 - age / lifetime)
