from __future__ import annotations

import math
from typing import Any, Sequence

import numpy as np

BOARD_CENTER = 50.0
RADIAL_SCALE = 70.0
STEP_SCALE = 500.0
SHIP_SCALE = 100.0
ROTATION_RADIUS_LIMIT = 50.0
COMET_SLOTS = 4
MAX_PLANET_SLOTS = 40
MAX_BODY_SLOTS = COMET_SLOTS + MAX_PLANET_SLOTS
ROUTE_ETA_UNREACHABLE = 1.0

# Backward-compatible metadata names used by existing processed shards.
PLANET_SLOTS = MAX_PLANET_SLOTS
N_BODY_SLOTS = MAX_BODY_SLOTS

FEATURE_NAMES = [
    "step_div_500",
    "production",
    "radial_div_70",
    "angle",
    "my_ships",
    "neutral_ships",
    "enemy_ships",
]
LEGACY_BOTH_FEATURE_NAMES = [
    "step_div_500",
    "production",
    "radial_div_70",
    "angle",
    "my_ships",
    "neutral_ships",
    "enemy1_ships",
    "enemy2_ships",
    "enemy3_ships",
]
BOTH_FEATURE_NAMES = [
    *LEGACY_BOTH_FEATURE_NAMES,
    "ships_for_capture",
]
MAX_ENEMY_CHANNELS = 3
ENEMY_FEATURE_START = 6
SHIPS_FOR_CAPTURE_FEATURE_INDEX = 9
RADIAL_FEATURE_INDEX = 2
ANGLE_FEATURE_INDEX = 3
ROTATION_BATCH_SIZE = 4


def torch_module() -> Any:
    import torch

    return torch


def numpy_to_torch(value: np.ndarray, *, bf16: bool = False) -> Any:
    torch = torch_module()
    tensor = torch.from_numpy(value)
    return tensor.to(torch.bfloat16) if bf16 else tensor


def feature_names_for_mode(mode: Any) -> list[str]:
    normalized = str(mode).strip().lower()
    if normalized == "both":
        return BOTH_FEATURE_NAMES.copy()
    if normalized in {"both_legacy", "legacy_both", "both9", "both_9"}:
        return LEGACY_BOTH_FEATURE_NAMES.copy()
    return FEATURE_NAMES.copy()


def value_i64(value: Any, default: int | None = None) -> int | None:
    if isinstance(value, bool) or value in (None, ""):
        return default
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def value_f64(value: Any, default: float | None = None) -> float | None:
    if isinstance(value, bool) or value in (None, ""):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def parse_planet(row: Any) -> dict[str, Any] | None:
    if not isinstance(row, list) or len(row) < 7:
        return None
    planet_id = value_i64(row[0])
    owner = value_i64(row[1])
    x = value_f64(row[2])
    y = value_f64(row[3])
    radius = value_f64(row[4])
    ships = value_i64(row[5])
    production = value_i64(row[6])
    if None in (planet_id, owner, x, y, radius, ships, production):
        return None
    return {
        "id": planet_id,
        "owner": owner,
        "x": x,
        "y": y,
        "radius": radius,
        "ships": ships,
        "production": production,
    }


def parse_planets(obs: dict[str, Any]) -> list[dict[str, Any]]:
    return [planet for row in obs.get("planets", []) if (planet := parse_planet(row)) is not None]


def comet_ids_in_slot_order(obs: dict[str, Any]) -> list[int]:
    ids: list[int] = []
    for group in obs.get("comets", []) or []:
        for pid in group.get("planet_ids", []) or []:
            parsed = value_i64(pid)
            if parsed is not None and parsed not in ids:
                ids.append(parsed)
    visible_comet_ids = set(obs.get("comet_planet_ids", []) or [])
    for pid in obs.get("comet_planet_ids", []) or []:
        parsed = value_i64(pid)
        if parsed is not None and parsed in visible_comet_ids and parsed not in ids:
            ids.append(parsed)
    return ids[:COMET_SLOTS]


def body_index(planet_id: int, comet_slot_by_id: dict[int, int], n_planets: int) -> int | None:
    if planet_id in comet_slot_by_id:
        return comet_slot_by_id[planet_id]
    idx = planet_id + COMET_SLOTS
    if COMET_SLOTS <= idx < n_planets:
        return idx
    return None


def body_indices(obs: dict[str, Any], n_planets: int) -> dict[int, int]:
    comet_slot_by_id = {pid: i for i, pid in enumerate(comet_ids_in_slot_order(obs))}
    out: dict[int, int] = {}
    for planet in parse_planets(obs):
        idx = body_index(planet["id"], comet_slot_by_id, n_planets)
        if idx is not None:
            out[planet["id"]] = idx
    return out


def body_slot_count(obs: dict[str, Any]) -> int:
    """Return the actual slot axis needed for this observation.

    Preprocessed training shards are padded to MAX_BODY_SLOTS, but the live game
    can have fewer regular planets. Comet slots are always reserved as a prefix;
    regular planets use slot = planet_id + COMET_SLOTS.
    """
    comet_ids = set(comet_ids_in_slot_order(obs))
    max_idx = COMET_SLOTS - 1
    for planet in parse_planets(obs):
        planet_id = int(planet["id"])
        if planet_id in comet_ids:
            continue
        idx = planet_id + COMET_SLOTS
        if idx >= COMET_SLOTS:
            max_idx = max(max_idx, idx)
    return max_idx + 1


def initial_planets_by_id(obs: dict[str, Any]) -> dict[int, dict[str, Any]]:
    return {
        planet["id"]: planet
        for row in obs.get("initial_planets", []) or []
        if (planet := parse_planet(row)) is not None
    }


def comet_position(obs: dict[str, Any], planet_id: int, dt: int) -> tuple[float, float] | None:
    for group in obs.get("comets", []) or []:
        ids = [value_i64(pid) for pid in group.get("planet_ids", []) or []]
        try:
            idx = ids.index(planet_id)
        except ValueError:
            continue
        path_index = value_i64(group.get("path_index"), 0) or 0
        future_index = path_index + dt
        if future_index < 0:
            return None
        paths = group.get("paths", []) or []
        if idx >= len(paths) or future_index >= len(paths[idx]):
            return None
        point = paths[idx][future_index]
        if not isinstance(point, list) or len(point) < 2:
            return None
        x = value_f64(point[0])
        y = value_f64(point[1])
        if x is None or y is None:
            return None
        return x, y
    return None


def planet_position(
    obs: dict[str, Any],
    planet: dict[str, Any],
    initial_by_id: dict[int, dict[str, Any]],
    is_comet: bool,
    dt: int,
) -> tuple[float, float] | None:
    if is_comet:
        return comet_position(obs, planet["id"], dt)

    initial = initial_by_id.get(planet["id"], planet)
    dx = initial["x"] - BOARD_CENTER
    dy = initial["y"] - BOARD_CENTER
    orbital_radius = math.hypot(dx, dy)
    if orbital_radius + planet["radius"] >= ROTATION_RADIUS_LIMIT:
        return planet["x"], planet["y"]

    step = value_i64(obs.get("step"), 0) or 0
    angular_velocity = value_f64(obs.get("angular_velocity"), 0.04) or 0.04
    phase_step = max(step + dt - 1, 0)
    angle = math.atan2(dy, dx) + angular_velocity * phase_step
    return (
        BOARD_CENTER + orbital_radius * math.cos(angle),
        BOARD_CENTER + orbital_radius * math.sin(angle),
    )


def polar_features(x: float, y: float) -> tuple[float, float]:
    dx = x - BOARD_CENTER
    dy = y - BOARD_CENTER
    radial = math.hypot(dx, dy) / RADIAL_SCALE
    angle = math.atan2(dy, dx)
    if angle < 0:
        angle += 2.0 * math.pi
    return radial, angle


def state_at(
    states_by_id: dict[int, list[list[int] | None]],
    planet_id: int,
    dt: int,
) -> tuple[int, int] | None:
    states = states_by_id.get(planet_id)
    if not states:
        return None
    idx = min(dt, len(states) - 1)
    row = states[idx]
    if row is None:
        return None
    return int(row[0]), int(row[1])


def comet_paths_by_id(obs: dict[str, Any]) -> dict[int, tuple[int, np.ndarray]]:
    paths_by_id: dict[int, tuple[int, np.ndarray]] = {}
    for group in obs.get("comets", []) or []:
        path_index = value_i64(group.get("path_index"), 0) or 0
        ids = [value_i64(pid) for pid in group.get("planet_ids", []) or []]
        paths = group.get("paths", []) or []
        for idx, planet_id in enumerate(ids):
            if planet_id is None or idx >= len(paths):
                continue
            points = []
            for point in paths[idx]:
                if not isinstance(point, list) or len(point) < 2:
                    continue
                x = value_f64(point[0])
                y = value_f64(point[1])
                if x is not None and y is not None:
                    points.append((x, y))
            if points:
                paths_by_id[planet_id] = (path_index, np.asarray(points, dtype=np.float32))
    return paths_by_id


ProjectedStateMap = dict[int, tuple[np.ndarray, np.ndarray, np.ndarray] | list[list[int] | None]]
ShipsForCaptureMap = dict[int, tuple[np.ndarray, np.ndarray] | np.ndarray | list[int | None]]


def active_enemy_players(states_by_id: ProjectedStateMap, player: int) -> list[int]:
    enemy_ids: set[int] = set()
    for states in states_by_id.values():
        if isinstance(states, tuple):
            owners, _ships, valid = states
            valid_mask = np.asarray(valid, dtype=bool)
            if not valid_mask.any():
                continue
            for owner in np.unique(np.asarray(owners, dtype=np.int64)[valid_mask]):
                owner_int = int(owner)
                if owner_int >= 0 and owner_int != player:
                    enemy_ids.add(owner_int)
            continue

        for state in states:
            if state is None:
                continue
            owner_int = int(state[0])
            if owner_int >= 0 and owner_int != player:
                enemy_ids.add(owner_int)
    return sorted(enemy_ids)


def enemy_feature_by_owner(
    states_by_id: ProjectedStateMap,
    player: int,
    enemy_player_order: Sequence[int] | None = None,
) -> dict[int, int]:
    active_ids = active_enemy_players(states_by_id, player)
    active_set = set(active_ids)
    ordered: list[int] = []
    if enemy_player_order is not None:
        for owner in enemy_player_order:
            owner_int = value_i64(owner)
            if owner_int is not None and owner_int in active_set and owner_int not in ordered:
                ordered.append(owner_int)
    for owner in active_ids:
        if owner not in ordered:
            ordered.append(owner)
    return {
        owner: ENEMY_FEATURE_START + idx
        for idx, owner in enumerate(ordered[:MAX_ENEMY_CHANNELS])
    }


def build_time_mask(
    obs: dict[str, Any],
    max_timesteps: int,
    *,
    return_torch_tensors: bool = True,
) -> Any:
    step = value_i64(obs.get("step"), 0) or 0
    dts = np.arange(max_timesteps, dtype=np.int64)
    mask = step + dts <= 500
    return numpy_to_torch(mask) if return_torch_tensors else mask


def projected_state_arrays(
    states_by_id: ProjectedStateMap,
    planet_id: int,
    feature_dts: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    states = states_by_id.get(planet_id)
    if states is None or (not isinstance(states, tuple) and not states):
        zeros = np.zeros(feature_dts.shape[0], dtype=np.int64)
        return zeros, zeros, np.zeros(feature_dts.shape[0], dtype=bool)

    if isinstance(states, tuple):
        owners, ships, valid = states
        state_len = len(owners)
    else:
        owners = np.asarray([0 if state is None else int(state[0]) for state in states], dtype=np.int64)
        ships = np.asarray([0 if state is None else int(state[1]) for state in states], dtype=np.int64)
        valid = np.asarray([state is not None for state in states], dtype=bool)
        state_len = len(states)
    idx = np.minimum(feature_dts, state_len - 1)
    return owners[idx], ships[idx], valid[idx]


def ships_for_capture_arrays(
    ships_for_capture_by_id: ShipsForCaptureMap | None,
    planet_id: int,
    player: int,
    owners: np.ndarray,
    ships: np.ndarray,
    valid: np.ndarray,
    feature_dts: np.ndarray,
) -> np.ndarray:
    capture_values = None if ships_for_capture_by_id is None else ships_for_capture_by_id.get(planet_id)
    if capture_values is not None:
        if isinstance(capture_values, tuple):
            needs, need_valid = capture_values
        else:
            values = capture_values
            if isinstance(values, np.ndarray):
                needs = values
                need_valid = np.ones(values.shape[0], dtype=bool)
            else:
                needs = np.asarray([0 if value is None else int(value) for value in values], dtype=np.int64)
                need_valid = np.asarray([value is not None for value in values], dtype=bool)
        needs = np.asarray(needs, dtype=np.int64)
        need_valid = np.asarray(need_valid, dtype=bool)
        if needs.size:
            idx = np.minimum(feature_dts, needs.shape[0] - 1)
            return np.where(need_valid[idx] & valid, np.maximum(needs[idx], 0), 0).astype(np.int64)

    return np.where((owners == player) | ~valid, 0, np.maximum(ships, 0) + 1).astype(np.int64)


def position_arrays(
    obs: dict[str, Any],
    planet: dict[str, Any],
    initial_by_id: dict[int, dict[str, Any]],
    comet_paths: dict[int, tuple[int, np.ndarray]],
    is_comet: bool,
    feature_dts: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    size = feature_dts.shape[0]
    if is_comet:
        path_info = comet_paths.get(planet["id"])
        if path_info is None:
            zeros = np.zeros(size, dtype=np.float32)
            return zeros, zeros, np.zeros(size, dtype=bool)
        path_index, path = path_info
        path_idx = path_index + feature_dts
        valid = (path_idx >= 0) & (path_idx < len(path))
        xs = np.zeros(size, dtype=np.float32)
        ys = np.zeros(size, dtype=np.float32)
        if valid.any():
            xs[valid] = path[path_idx[valid], 0]
            ys[valid] = path[path_idx[valid], 1]
        return xs, ys, valid

    initial = initial_by_id.get(planet["id"], planet)
    dx = initial["x"] - BOARD_CENTER
    dy = initial["y"] - BOARD_CENTER
    orbital_radius = math.hypot(dx, dy)
    valid = np.ones(size, dtype=bool)
    if orbital_radius + planet["radius"] >= ROTATION_RADIUS_LIMIT:
        xs = np.full(size, planet["x"], dtype=np.float32)
        ys = np.full(size, planet["y"], dtype=np.float32)
        return xs, ys, valid

    step = value_i64(obs.get("step"), 0) or 0
    angular_velocity = value_f64(obs.get("angular_velocity"), 0.04) or 0.04
    phase_steps = np.maximum(step + feature_dts - 1, 0).astype(np.float32)
    angles = np.float32(math.atan2(dy, dx)) + np.float32(angular_velocity) * phase_steps
    xs = BOARD_CENTER + np.float32(orbital_radius) * np.cos(angles, dtype=np.float32)
    ys = BOARD_CENTER + np.float32(orbital_radius) * np.sin(angles, dtype=np.float32)
    return xs.astype(np.float32), ys.astype(np.float32), valid


def build_feature_tensor(
    obs: dict[str, Any],
    player: int,
    max_timesteps: int,
    n_planets: int,
    states_by_id: ProjectedStateMap,
    enemy_player_order: Sequence[int] | None = None,
    feature_names: Sequence[str] | None = None,
    ships_for_capture_by_id: ShipsForCaptureMap | None = None,
    rotation_idx: int = 0,
    return_torch_tensors: bool = True,
) -> Any:
    feature_names = list(FEATURE_NAMES if feature_names is None else feature_names)
    split_enemy_features = feature_names in (BOTH_FEATURE_NAMES, LEGACY_BOTH_FEATURE_NAMES)
    has_ships_for_capture = "ships_for_capture" in feature_names
    if feature_names != FEATURE_NAMES and not split_enemy_features:
        raise ValueError(f"unsupported feature layout: {feature_names!r}")

    x = np.zeros((n_planets, max_timesteps, len(feature_names)), dtype=np.float32)
    planets = parse_planets(obs)
    initial_by_id = initial_planets_by_id(obs)
    comet_ids = set(comet_ids_in_slot_order(obs))
    comet_paths = comet_paths_by_id(obs)
    indices = body_indices(obs, n_planets)
    step = value_i64(obs.get("step"), 0) or 0
    dts = np.arange(max_timesteps, dtype=np.int64)
    time_valid = step + dts <= 500
    feature_dts = np.minimum(dts, max(0, 500 - step))
    step_feature = (step + dts).astype(np.float32) / np.float32(STEP_SCALE)
    enemy_features = (
        enemy_feature_by_owner(states_by_id, player, enemy_player_order)
        if split_enemy_features
        else {}
    )

    for planet in planets:
        idx = indices.get(planet["id"])
        if idx is None:
            continue
        is_comet = planet["id"] in comet_ids
        owners, ships, state_valid = projected_state_arrays(states_by_id, planet["id"], feature_dts)

        slot = x[idx]
        comet_path_info = comet_paths.get(planet["id"]) if is_comet else None
        if comet_path_info is not None and comet_path_info[0] < 0:
            valid = state_valid & time_valid
            slot[valid, 0] = step_feature[valid]
            continue

        xs, ys, position_valid = position_arrays(
            obs, planet, initial_by_id, comet_paths, is_comet, feature_dts
        )
        valid = state_valid & position_valid & time_valid
        if not valid.any():
            continue

        dx = xs - np.float32(BOARD_CENTER)
        dy = ys - np.float32(BOARD_CENTER)
        radial = np.sqrt(dx * dx + dy * dy, dtype=np.float32) / np.float32(RADIAL_SCALE)
        angle = np.arctan2(dy, dx).astype(np.float32)
        angle = np.where(angle < 0.0, angle + np.float32(2.0 * math.pi), angle)
        ships_scaled = ships[valid].astype(np.float32) / np.float32(SHIP_SCALE)

        slot[valid, 0] = step_feature[valid]
        slot[valid, 1] = np.float32(planet["production"])
        slot[valid, 2] = radial[valid]
        slot[valid, 3] = angle[valid]
        slot[valid, 4] = np.where(owners[valid] == player, ships_scaled, 0).astype(np.float32)
        slot[valid, 5] = np.where(owners[valid] == -1, ships_scaled, 0).astype(np.float32)
        valid_owners = owners[valid]
        if split_enemy_features:
            for owner, feature_idx in enemy_features.items():
                slot[valid, feature_idx] = np.where(
                    valid_owners == owner, ships_scaled, 0
                ).astype(np.float32)
            if has_ships_for_capture:
                capture_ships = ships_for_capture_arrays(
                    ships_for_capture_by_id,
                    planet["id"],
                    player,
                    owners,
                    ships,
                    state_valid,
                    feature_dts,
                )
                slot[valid, SHIPS_FOR_CAPTURE_FEATURE_INDEX] = (
                    capture_ships[valid].astype(np.float32) / np.float32(SHIP_SCALE)
                )
        else:
            slot[valid, 6] = np.where(
                (valid_owners != -1) & (valid_owners != player), ships_scaled, 0
            ).astype(np.float32)

    apply_quarter_turn_rotation(x, rotation_idx)
    return numpy_to_torch(x, bf16=True) if return_torch_tensors else x


def apply_quarter_turn_rotation(x: np.ndarray, rotation_idx: int) -> np.ndarray:
    if x.shape[-1] <= ANGLE_FEATURE_INDEX:
        raise ValueError(f"feature tensor has no angle channel: shape {x.shape}")

    rotation_idx = int(rotation_idx) % ROTATION_BATCH_SIZE
    if rotation_idx == 0:
        return x

    position_populated = (
        (x[..., RADIAL_FEATURE_INDEX] != 0.0)
        | (x[..., ANGLE_FEATURE_INDEX] != 0.0)
    )
    base_angle = x[..., ANGLE_FEATURE_INDEX]
    rotated_angle = np.mod(
        base_angle + np.float32(rotation_idx) * np.float32(0.5 * math.pi),
        np.float32(2.0 * math.pi),
    )
    x[..., ANGLE_FEATURE_INDEX] = np.where(position_populated, rotated_angle, base_angle)
    return x


def build_rotated_feature_batch(x: np.ndarray) -> np.ndarray:
    if x.ndim != 3:
        raise ValueError(f"expected unbatched feature tensor with 3 dims, got shape {x.shape}")
    if x.shape[-1] <= ANGLE_FEATURE_INDEX:
        raise ValueError(f"feature tensor has no angle channel: shape {x.shape}")

    batch = np.repeat(x[None, ...], ROTATION_BATCH_SIZE, axis=0)
    for rotation_idx in range(1, ROTATION_BATCH_SIZE):
        apply_quarter_turn_rotation(batch[rotation_idx], rotation_idx)
    return batch


def build_body_mask(
    obs: dict[str, Any],
    n_planets: int,
    states_by_id: ProjectedStateMap,
    *,
    return_torch_tensors: bool = True,
) -> Any:
    mask = np.zeros(n_planets, dtype=bool)
    comet_ids = set(comet_ids_in_slot_order(obs))
    indices = body_indices(obs, n_planets)
    for planet in parse_planets(obs):
        idx = indices.get(planet["id"])
        if idx is None:
            continue
        if planet["id"] in comet_ids:
            states = states_by_id.get(planet["id"], [])
            if isinstance(states, tuple):
                mask[idx] = bool(states[2].any())
            else:
                mask[idx] = any(state is not None for state in states)
        else:
            mask[idx] = True
    return numpy_to_torch(mask) if return_torch_tensors else mask


def build_output_tensors(
    obs: dict[str, Any],
    player: int,
    n_planets: int,
    actual_targets: dict[int, int],
    candidate_pairs: list[tuple[int, int]],
    *,
    actual_fleet_fractions: dict[int, int] | None = None,
    candidate_fleet_fractions: list[tuple[int, int]] | None = None,
    route_eta_by_fraction: list[tuple[int, int, int, int]] | None = None,
    include_route_eta_by_fraction: bool = False,
    n_fleet_fractions: int | None = None,
    n_route_eta_fractions: int | None = None,
    return_torch_tensors: bool = True,
) -> dict[str, Any]:
    launch_mask = np.zeros(n_planets, dtype=bool)
    launch = np.zeros(n_planets, dtype=bool)
    target_mask = np.zeros((n_planets, n_planets), dtype=bool)
    target = np.zeros((n_planets, n_planets), dtype=bool)

    indices = body_indices(obs, n_planets)
    for planet in parse_planets(obs):
        idx = indices.get(planet["id"])
        if idx is not None and planet["owner"] == player:
            launch_mask[idx] = True

    for source_id, target_id in candidate_pairs:
        source_idx = indices.get(source_id)
        target_idx = indices.get(target_id)
        if (
            source_idx is not None
            and target_idx is not None
            and source_idx != target_idx
            and launch_mask[source_idx]
        ):
            target_mask[source_idx, target_idx] = True

    for source_id, target_id in actual_targets.items():
        source_idx = indices.get(source_id)
        target_idx = indices.get(target_id)
        valid_target = (
            source_idx is not None
            and target_idx is not None
            and target_mask[source_idx, target_idx]
        )
        if valid_target:
            launch[source_idx] = True
            target[source_idx, target_idx] = True

    outputs = {
        "launch_mask": launch_mask,
        "launch": launch,
        "target_mask": target_mask,
        "target": target,
    }
    if include_route_eta_by_fraction:
        if n_route_eta_fractions is None:
            if n_fleet_fractions is not None:
                n_route_eta_fractions = n_fleet_fractions
            elif route_eta_by_fraction:
                n_route_eta_fractions = (
                    max(index for _source, _target, index, _eta in route_eta_by_fraction) + 1
                )
            else:
                n_route_eta_fractions = 0
        route_eta = np.full(
            (n_planets, n_planets, n_route_eta_fractions),
            ROUTE_ETA_UNREACHABLE,
            dtype=np.float32,
        )

        for source_id, target_id, fraction_index, eta in route_eta_by_fraction or []:
            source_idx = indices.get(source_id)
            target_idx = indices.get(target_id)
            if (
                source_idx is None
                or target_idx is None
                or source_idx == target_idx
                or not launch_mask[source_idx]
                or not (0 <= fraction_index < n_route_eta_fractions)
                or eta <= 0
                or eta > STEP_SCALE
            ):
                continue
            normalized_eta = float(eta) / STEP_SCALE
            current_eta = route_eta[source_idx, target_idx, fraction_index]
            if current_eta == ROUTE_ETA_UNREACHABLE or normalized_eta < float(current_eta):
                route_eta[source_idx, target_idx, fraction_index] = normalized_eta
        outputs["route_eta_by_fraction"] = route_eta

    if (
        n_fleet_fractions is not None
        or actual_fleet_fractions is not None
        or candidate_fleet_fractions is not None
    ):
        if n_fleet_fractions is None:
            max_index = -1
            if actual_fleet_fractions:
                max_index = max(max_index, max(actual_fleet_fractions.values()))
            if candidate_fleet_fractions:
                max_index = max(max_index, max(index for _source, index in candidate_fleet_fractions))
            n_fleet_fractions = max_index + 1
        fleet_fraction = np.zeros((n_planets, n_fleet_fractions), dtype=bool)
        fleet_fraction_mask = np.zeros((n_planets, n_fleet_fractions), dtype=bool)

        for source_id, fraction_index in candidate_fleet_fractions or []:
            source_idx = indices.get(source_id)
            if (
                source_idx is not None
                and launch_mask[source_idx]
                and 0 <= fraction_index < n_fleet_fractions
            ):
                fleet_fraction_mask[source_idx, fraction_index] = True

        for source_id, fraction_index in (actual_fleet_fractions or {}).items():
            source_idx = indices.get(source_id)
            if source_idx is None or not launch[source_idx]:
                continue
            if 0 <= fraction_index < n_fleet_fractions:
                fleet_fraction[source_idx, fraction_index] = True
                fleet_fraction_mask[source_idx, fraction_index] = True

        outputs["fleet_fraction"] = fleet_fraction
        outputs["fleet_fraction_mask"] = fleet_fraction_mask
    if not return_torch_tensors:
        return outputs
    return {key: numpy_to_torch(value) for key, value in outputs.items()}
