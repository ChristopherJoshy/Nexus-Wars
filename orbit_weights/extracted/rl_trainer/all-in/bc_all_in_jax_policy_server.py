#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
import time
import traceback
from pathlib import Path
from typing import Any


STARTED = time.perf_counter()
FIRST_INFERENCE = True
SEEN_INFERENCE_SHAPES: set[tuple[int, int, int]] = set()
TIMING_LOG_INTERVAL = 10
LOCAL_ARENA_ENV = "ORBIT_WARS_BC_ALL_IN_LOCAL_ARENA"
STARTUP_METRICS: dict[str, Any] = {}
ENSEMBLE_MANIFEST_KEY = "__ensemble_manifest_json"
ENEMY_FEATURE_INDICES = (6, 7, 8)
ENEMY_IDENTITY_PERMUTATION = ENEMY_FEATURE_INDICES
ENEMY_TTA_4_REMAINING_SCHEDULE = (
    (ENEMY_IDENTITY_PERMUTATION, 0),
    (ENEMY_IDENTITY_PERMUTATION, 1),
    ((6, 8, 7), 0),
    ((7, 6, 8), 1),
    ((7, 8, 6), 2),
    ((8, 6, 7), 3),
    ((8, 7, 6), 2),
    ((8, 7, 6), 3),
)
ENEMY_TTA_3_REMAINING_SCHEDULE = tuple(
    (permutation, rotation_idx)
    for permutation in (ENEMY_IDENTITY_PERMUTATION, (7, 6, 8))
    for rotation_idx in range(4)
)


def max_timesteps_from_env() -> int:
    raw = os.environ.get("ORBIT_WARS_BC_ALL_IN_MAX_TIMESTEPS")
    if not raw:
        raise RuntimeError("ORBIT_WARS_BC_ALL_IN_MAX_TIMESTEPS is required")
    try:
        value = int(raw)
    except ValueError:
        raise RuntimeError(f"invalid ORBIT_WARS_BC_ALL_IN_MAX_TIMESTEPS={raw!r}") from None
    if value <= 0:
        raise RuntimeError(f"invalid ORBIT_WARS_BC_ALL_IN_MAX_TIMESTEPS={raw!r}")
    return value


def positive_int_env(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    try:
        value = int(raw)
    except ValueError:
        raise RuntimeError(f"invalid {name}={raw!r}") from None
    if value <= 0:
        raise RuntimeError(f"invalid {name}={raw!r}")
    return value


def optional_positive_int_env(name: str) -> int | None:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return None
    try:
        value = int(raw)
    except ValueError:
        raise RuntimeError(f"invalid {name}={raw!r}") from None
    if value <= 0:
        raise RuntimeError(f"invalid {name}={raw!r}")
    return value


def local_arena_enabled() -> bool:
    return os.environ.get(LOCAL_ARENA_ENV) == "1"


def local_fixed_body_slots() -> int | None:
    if not local_arena_enabled():
        return None
    return positive_int_env("ORBIT_WARS_BC_ALL_IN_FIXED_BODY_SLOTS", 44)


def local_max_timesteps(configured_max_timesteps: int) -> int:
    if not local_arena_enabled():
        return configured_max_timesteps
    return positive_int_env("ORBIT_WARS_BC_ALL_IN_FIXED_TIMESTEPS", configured_max_timesteps)


def max_batch_requests_from_env() -> int | None:
    return optional_positive_int_env("ORBIT_WARS_BC_ALL_IN_MAX_BATCH_REQUESTS")


def next_power_of_two(value: int) -> int:
    if value <= 1:
        return 1
    return 1 << (value - 1).bit_length()


def detailed_logging_enabled() -> bool:
    return os.environ.get("ORBIT_WARS_BC_ALL_IN_LOG_TIMINGS") == "1"


def compact_logging_enabled() -> bool:
    return os.environ.get("ORBIT_WARS_BC_ALL_IN_LOG_TIMINGS") != "0"


def log_status(status: str, **fields: Any) -> None:
    if not detailed_logging_enabled() and status not in {
        "fatal",
        "first_inference_summary",
        "inference_error",
    }:
        return
    if not compact_logging_enabled() and status != "fatal":
        return
    parts = [f"agent_nn_jax status={status}", f"elapsed_ms={(time.perf_counter() - STARTED) * 1000.0:.1f}"]
    for key, value in fields.items():
        text = str(value).replace("\n", " ")[:300]
        parts.append(f"{key}={text}")
    print(" ".join(parts), file=sys.stderr, flush=True)


def should_log_timing(request_id: int, rotation_tta: bool) -> bool:
    configured = os.environ.get("ORBIT_WARS_BC_ALL_IN_LOG_TIMINGS")
    if configured == "1":
        return True
    return False


def owner_from_row(row: Any, owner_index: int = 1) -> int | None:
    if not isinstance(row, (list, tuple)) or len(row) <= owner_index:
        return None
    try:
        return int(float(row[owner_index]))
    except (TypeError, ValueError):
        return None


def observed_active_player_count(obs: dict[str, Any]) -> int:
    owners: set[int] = set()
    for row in obs.get("planets", []) or []:
        owner = owner_from_row(row)
        if owner is not None and owner >= 0:
            owners.add(owner)
    for row in obs.get("fleets", []) or []:
        owner = owner_from_row(row)
        if owner is not None and owner >= 0:
            owners.add(owner)
    return len(owners)


def enemy_tta_schedule(
    remaining_players: int,
    *,
    rotation_tta: bool,
    force_eight_views: bool = False,
) -> tuple[tuple[tuple[int, int, int], int], ...]:
    if rotation_tta:
        if remaining_players >= 4:
            return ENEMY_TTA_4_REMAINING_SCHEDULE
        if remaining_players == 3:
            return ENEMY_TTA_3_REMAINING_SCHEDULE
        base_schedule = tuple((ENEMY_IDENTITY_PERMUTATION, rotation_idx) for rotation_idx in range(4))
        return base_schedule + base_schedule if force_eight_views else base_schedule

    if remaining_players >= 4:
        return tuple(
            (permutation, 0)
            for permutation in (
                ENEMY_IDENTITY_PERMUTATION,
                (6, 8, 7),
                (7, 6, 8),
                (7, 8, 6),
                (8, 6, 7),
                (8, 7, 6),
            )
        )
    if remaining_players == 3:
        return ((ENEMY_IDENTITY_PERMUTATION, 0), ((7, 6, 8), 0))
    return ((ENEMY_IDENTITY_PERMUTATION, 0),)


def build_enemy_tta_feature_batch(
    x_base: Any,
    np_module: Any,
    *,
    remaining_players: int,
    rotation_tta: bool,
    force_eight_views: bool,
    apply_quarter_turn_rotation: Any,
) -> Any:
    schedule = enemy_tta_schedule(
        remaining_players,
        rotation_tta=rotation_tta,
        force_eight_views=force_eight_views,
    )
    x = np_module.repeat(x_base[None, ...], len(schedule), axis=0)
    for view_idx, (permutation, rotation_idx) in enumerate(schedule):
        view = x[view_idx]
        if permutation != ENEMY_IDENTITY_PERMUTATION:
            for dst_idx, src_idx in zip(ENEMY_FEATURE_INDICES, permutation):
                view[..., dst_idx] = x_base[..., src_idx]
        if rotation_idx:
            apply_quarter_turn_rotation(view, rotation_idx)
    return x


def workspace_root() -> Path:
    return Path(__file__).resolve().parents[2]


def configure_imports() -> Path:
    root = workspace_root()
    trainer_dir = root / "rl_trainer" / "all-in"
    sys.path.insert(0, str(trainer_dir))
    return root


def resolve_model_path(root: Path) -> Path:
    configured = os.environ.get("ORBIT_WARS_BC_ALL_IN_MODEL")
    if not configured:
        raise RuntimeError("ORBIT_WARS_BC_ALL_IN_MODEL is required")
    path = Path(configured).expanduser()
    return path if path.is_absolute() else root / path


def decode_ensemble_manifest(raw: Any) -> dict[str, Any]:
    import numpy as np

    data = np.asarray(raw, dtype=np.uint8).tobytes()
    return json.loads(data.decode("utf-8"))


def load_policy_params(model_path: Path, jnp_module: Any) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    import numpy as np

    with np.load(model_path) as npz:
        if ENSEMBLE_MANIFEST_KEY not in npz.files:
            params = {
                key: jnp_module.asarray(npz[key])
                for key in npz.files
                if not key.startswith("__")
            }
            return [params], None

        manifest = decode_ensemble_manifest(npz[ENSEMBLE_MANIFEST_KEY])
        member_count = int(manifest.get("member_count", 0))
        array_keys = list(manifest.get("array_keys", []))
        if member_count <= 0 or not array_keys:
            raise RuntimeError(f"invalid ensemble manifest in {model_path}")

        members: list[dict[str, Any]] = []
        for member_idx in range(member_count):
            prefix = f"member_{member_idx}/"
            member: dict[str, Any] = {}
            for key in array_keys:
                packed_key = prefix + key
                if packed_key not in npz.files:
                    raise RuntimeError(f"ensemble artifact missing {packed_key}")
                member[key] = jnp_module.asarray(npz[packed_key])
            members.append(member)
        return members, manifest


def configure_jax_env() -> None:
    local_arena = local_arena_enabled()
    if local_arena:
        os.environ.setdefault("JAX_PLATFORM_NAME", "cuda")
        os.environ.setdefault("JAX_PLATFORMS", "cuda")
    else:
        os.environ.setdefault("JAX_PLATFORM_NAME", "cpu")
        os.environ.setdefault("JAX_PLATFORMS", "cpu")
        os.environ.setdefault(
            "XLA_FLAGS",
            "--xla_cpu_multi_thread_eigen=false intra_op_parallelism_threads=1",
        )


def load_policy(root: Path):
    configure_jax_env()
    model_path = resolve_model_path(root)
    configured_max_timesteps = max_timesteps_from_env()
    max_timesteps = local_max_timesteps(configured_max_timesteps)
    fixed_body_slots = local_fixed_body_slots()
    STARTUP_METRICS["model_bytes"] = model_path.stat().st_size if model_path.is_file() else "missing"
    import_started = time.perf_counter()
    log_status("import_jax_start")
    import jax
    import jax.numpy as jnp

    import_done = time.perf_counter()
    STARTUP_METRICS["import_jax_ms"] = (import_done - import_started) * 1000.0
    STARTUP_METRICS["jax_version"] = getattr(jax, "__version__", "unknown")
    STARTUP_METRICS["backend"] = jax.default_backend()
    log_status(
        "import_jax_done",
        jax_version=STARTUP_METRICS["jax_version"],
        backend=STARTUP_METRICS["backend"],
    )
    from bc_all_in_jax_model import jitted_fraction_head, jitted_planet_transformer

    log_status(
        "load_artifact_start",
        model_path=model_path,
        exists=model_path.is_file(),
        bytes=STARTUP_METRICS["model_bytes"],
    )
    load_started = time.perf_counter()
    params, ensemble_manifest = load_policy_params(model_path, jnp)
    load_done = time.perf_counter()
    STARTUP_METRICS["load_artifact_ms"] = (load_done - load_started) * 1000.0
    first_params = params[0]
    input_dim = int(first_params["planet_embedding.conv_blocks.0.conv1d.weight"].shape[1])
    feature_mode = os.environ.get("ORBIT_WARS_BC_ALL_IN_FEATURE_MODE") or (
        "both" if input_dim == 10 else "both_legacy" if input_dim == 9 else "2p"
    )
    rotation_tta = os.environ.get("ORBIT_WARS_BC_ALL_IN_ROTATION_TTA") == "1"
    enemy_tta = os.environ.get("ORBIT_WARS_BC_ALL_IN_ENEMY_TTA") == "1"
    conv_blocks = sum(
        1
        for key in first_params
        if key.startswith("planet_embedding.conv_blocks.") and key.endswith(".conv1d.weight")
    )
    encoder_layers = sum(
        1
        for key in first_params
        if key.startswith("encoder.layers.") and key.endswith(".attn.Wqkv.weight")
    )
    num_fleet_fractions = (
        int(first_params["fraction_head.mlp.2.bias"].shape[0])
        if "fraction_head.mlp.2.bias" in first_params
        else 0
    )
    pair_attention_input_dim = (
        int(first_params["pair_attention_bias.encoder.0.weight"].shape[1])
        if "pair_attention_bias.encoder.0.weight" in first_params
        else 0
    )
    ensemble_members = len(params)
    STARTUP_METRICS.update(
        arrays=len(first_params),
        ensemble_members=ensemble_members,
        artifact_format=(
            ensemble_manifest.get("format", "ensemble") if ensemble_manifest else "single_model"
        ),
        input_dim=input_dim,
        feature_mode=feature_mode,
        conv_blocks=conv_blocks,
        encoder_layers=encoder_layers,
        num_fleet_fractions=num_fleet_fractions,
        pair_attention_input_dim=pair_attention_input_dim,
        hidden_size=int(first_params["encoder.layers.0.attn.Wqkv.weight"].shape[1]),
        rotation_tta=rotation_tta,
        enemy_tta=enemy_tta,
        max_timesteps=max_timesteps,
        configured_max_timesteps=configured_max_timesteps,
        fixed_body_slots=fixed_body_slots or "dynamic",
        ready_ms=(time.perf_counter() - STARTED) * 1000.0,
    )
    log_status(
        "load_artifact_done",
        arrays=len(first_params),
        input_dim=input_dim,
        ensemble_members=ensemble_members,
        artifact_format=STARTUP_METRICS["artifact_format"],
    )
    log_status(
        "model_ready",
        feature_mode=feature_mode,
        conv_blocks=conv_blocks,
        encoder_layers=encoder_layers,
        hidden_size=STARTUP_METRICS["hidden_size"],
        ensemble_members=ensemble_members,
        rotation_tta=rotation_tta,
        enemy_tta=enemy_tta,
        max_timesteps=max_timesteps,
        configured_max_timesteps=configured_max_timesteps,
        fixed_body_slots=fixed_body_slots or "dynamic",
        num_fleet_fractions=num_fleet_fractions,
        pair_attention_input_dim=pair_attention_input_dim,
        prewarm_strategy="fixed_local_shape" if fixed_body_slots else "first_observed_body_shape",
        runtime="jax",
    )
    return (
        jax,
        jnp,
        jitted_planet_transformer,
        jitted_fraction_head,
        params,
        feature_mode,
        rotation_tta,
        enemy_tta,
        max_timesteps,
        fixed_body_slots,
        num_fleet_fractions,
        pair_attention_input_dim,
    )


def states_by_id_from_request(req: dict[str, Any], np_module: Any) -> dict[int, tuple[Any, Any, Any]]:
    states: dict[int, tuple[Any, Any, Any]] = {}
    for row in req.get("states", []):
        if not isinstance(row, list) or len(row) < 4:
            continue
        planet_id, owners, ships, valid = row[:4]
        states[int(planet_id)] = (
            np_module.asarray(owners, dtype=np_module.int64),
            np_module.asarray(ships, dtype=np_module.int64),
            np_module.asarray(valid, dtype=bool),
        )
    return states


def ships_for_capture_by_id_from_request(
    req: dict[str, Any],
    np_module: Any,
) -> dict[int, tuple[Any, Any]]:
    ships_for_capture: dict[int, tuple[Any, Any]] = {}
    for row in req.get("states", []):
        if not isinstance(row, list) or len(row) < 5:
            continue
        planet_id, _owners, _ships, valid, needs = row[:5]
        ships_for_capture[int(planet_id)] = (
            np_module.asarray(needs, dtype=np_module.int64),
            np_module.asarray(valid, dtype=bool),
        )
    return ships_for_capture


def masked_softmax_argmax(logits: Any, mask: Any, np_module: Any) -> tuple[int | None, float]:
    if not bool(mask.any()):
        return None, 0.0
    row = np_module.asarray(logits, dtype=np_module.float32)
    valid = np_module.asarray(mask, dtype=bool)
    masked = np_module.where(valid, row, -np_module.inf)
    max_value = float(np_module.max(masked))
    exps = np_module.where(valid, np_module.exp(masked - max_value), 0.0)
    denom = float(np_module.sum(exps))
    if denom <= 0.0 or not np_module.isfinite(denom):
        return None, 0.0
    probs = exps / denom
    target_idx = int(np_module.argmax(probs))
    return target_idx, float(probs[target_idx])


def compact_body_inputs(
    x: Any,
    body_mask: Any,
    launch_mask: Any,
    target_mask: Any,
    np_module: Any,
    reserved_prefix_slots: int = 0,
) -> tuple[Any, Any, Any, Any, Any]:
    active_indices = np_module.flatnonzero(np_module.asarray(body_mask[0], dtype=bool))
    if reserved_prefix_slots > 0:
        reserved = np_module.arange(min(reserved_prefix_slots, body_mask.shape[1]), dtype=active_indices.dtype)
        active_indices = np_module.union1d(reserved, active_indices)
    if active_indices.size == 0:
        active_indices = np_module.arange(body_mask.shape[1], dtype=np_module.int64)
    return (
        x[:, active_indices, :, :],
        body_mask[:, active_indices],
        launch_mask[:, active_indices],
        target_mask[:, active_indices, :][:, :, active_indices],
        active_indices,
    )


def scatter_compact_outputs(
    launch_prob_compact: Any,
    target_logits_compact: Any,
    active_indices: Any,
    n_bodies: int,
    np_module: Any,
) -> tuple[Any, Any]:
    launch_prob = np_module.zeros(n_bodies, dtype=np_module.float32)
    target_logits = np_module.full((n_bodies, n_bodies), -np_module.inf, dtype=np_module.float32)
    launch_prob[active_indices] = np_module.asarray(launch_prob_compact, dtype=np_module.float32)
    target_logits[np_module.ix_(active_indices, active_indices)] = np_module.asarray(
        target_logits_compact,
        dtype=np_module.float32,
    )
    return launch_prob, target_logits


def scatter_compact_fraction_outputs(
    fraction_logits_compact: Any,
    active_indices: Any,
    n_bodies: int,
    num_fleet_fractions: int,
    np_module: Any,
) -> Any:
    fraction_logits = np_module.full(
        (n_bodies, num_fleet_fractions),
        -np_module.inf,
        dtype=np_module.float32,
    )
    fraction_logits[active_indices] = np_module.asarray(
        fraction_logits_compact,
        dtype=np_module.float32,
    )
    return fraction_logits


def model_param_sets(params: Any) -> list[Any]:
    if isinstance(params, list):
        return params
    return [params]


def build_target_fraction_mask(
    req: dict[str, Any],
    indices: dict[int, int],
    n_bodies: int,
    num_fleet_fractions: int,
    target_mask: Any,
    launch_mask: Any,
    np_module: Any,
) -> Any:
    mask = np_module.zeros((n_bodies, n_bodies, num_fleet_fractions), dtype=bool)
    if num_fleet_fractions <= 0:
        return mask
    target_mask = np_module.asarray(target_mask, dtype=bool)
    launch_mask = np_module.asarray(launch_mask, dtype=bool)
    route_rows = req.get("route_eta_by_fraction")
    if route_rows is not None:
        for row in route_rows or []:
            if not isinstance(row, (list, tuple)) or len(row) < 4:
                continue
            source_id, target_id, fraction_index, eta = (
                int(row[0]),
                int(row[1]),
                int(row[2]),
                int(row[3]),
            )
            if eta <= 0 or not (0 <= fraction_index < num_fleet_fractions):
                continue
            source_idx = indices.get(source_id)
            target_idx = indices.get(target_id)
            if (
                source_idx is not None
                and target_idx is not None
                and 0 <= source_idx < n_bodies
                and 0 <= target_idx < n_bodies
                and bool(launch_mask[source_idx])
                and bool(target_mask[source_idx, target_idx])
            ):
                mask[source_idx, target_idx, fraction_index] = True
        return mask

    candidate_pairs_by_source: dict[int, list[int]] = {}
    for pair in req.get("candidates", []):
        if isinstance(pair, list) and len(pair) == 2:
            source_idx = indices.get(int(pair[0]))
            target_idx = indices.get(int(pair[1]))
            if source_idx is not None and target_idx is not None:
                candidate_pairs_by_source.setdefault(source_idx, []).append(target_idx)

    for row in req.get("fleet_fraction_candidates", []) or []:
        if not isinstance(row, list):
            continue
        if len(row) >= 3:
            source_id, target_id, fraction_index = int(row[0]), int(row[1]), int(row[2])
            source_idx = indices.get(source_id)
            target_idx = indices.get(target_id)
            target_indices = [target_idx] if target_idx is not None else []
        elif len(row) == 2:
            source_id, fraction_index = int(row[0]), int(row[1])
            source_idx = indices.get(source_id)
            target_indices = candidate_pairs_by_source.get(source_idx, []) if source_idx is not None else []
        else:
            continue
        if source_idx is None or not (0 <= fraction_index < num_fleet_fractions):
            continue
        if not bool(launch_mask[source_idx]):
            continue
        for target_idx in target_indices:
            if (
                target_idx is not None
                and 0 <= target_idx < n_bodies
                and bool(target_mask[source_idx, target_idx])
            ):
                mask[source_idx, target_idx, fraction_index] = True
    return mask


def prepare_request_inputs(
    req: dict[str, Any],
    np_module: Any,
    feature_mode: str,
    rotation_tta: bool,
    max_timesteps: int,
    fixed_body_slots: int | None,
    num_fleet_fractions: int,
    pair_attention_input_dim: int = 0,
    enemy_tta: bool = False,
) -> dict[str, Any]:
    from features import (
        COMET_SLOTS,
        apply_quarter_turn_rotation,
        body_slot_count,
        body_indices,
        build_body_mask,
        build_feature_tensor,
        build_output_tensors,
        build_rotated_feature_batch,
        build_time_mask,
        feature_names_for_mode,
    )

    request_id = int(req.get("id", -1))
    obs = req.get("observation")
    if not isinstance(obs, dict):
        return {
            "status": "ERR",
            "id": request_id,
            "error": "missing observation",
        }

    use_rotation_tta = rotation_tta
    player = int(req.get("player", obs.get("player", 0)))
    states_by_id = states_by_id_from_request(req, np_module)
    ships_for_capture_by_id = ships_for_capture_by_id_from_request(req, np_module)
    candidate_pairs = [
        (int(pair[0]), int(pair[1]))
        for pair in req.get("candidates", [])
        if isinstance(pair, list) and len(pair) == 2
    ]
    n_bodies = fixed_body_slots or body_slot_count(obs)

    feature_names = feature_names_for_mode(feature_mode)
    x_base = build_feature_tensor(
        obs,
        player,
        max_timesteps,
        n_bodies,
        states_by_id,
        feature_names=feature_names,
        ships_for_capture_by_id=ships_for_capture_by_id,
        return_torch_tensors=False,
    )
    if enemy_tta and use_rotation_tta and x_base.shape[-1] > ENEMY_FEATURE_INDICES[-1]:
        x = build_enemy_tta_feature_batch(
            x_base,
            np_module,
            remaining_players=observed_active_player_count(obs),
            rotation_tta=use_rotation_tta,
            force_eight_views=True,
            apply_quarter_turn_rotation=apply_quarter_turn_rotation,
        )
        batch_size = x.shape[0]
    elif use_rotation_tta:
        x = build_rotated_feature_batch(x_base)
        batch_size = x.shape[0]
    else:
        x = x_base[None, ...]
        batch_size = 1
    time_mask = np_module.broadcast_to(
        build_time_mask(obs, max_timesteps, return_torch_tensors=False),
        (batch_size, max_timesteps),
    )
    base_body_mask = build_body_mask(obs, n_bodies, states_by_id, return_torch_tensors=False)[
        None, :
    ]
    body_mask = np_module.broadcast_to(base_body_mask, (batch_size, n_bodies))
    output_tensors = build_output_tensors(
        obs,
        player,
        n_bodies,
        {},
        candidate_pairs,
        route_eta_by_fraction=[
            (int(row[0]), int(row[1]), int(row[2]), int(row[3]))
            for row in req.get("route_eta_by_fraction", []) or []
            if isinstance(row, (list, tuple)) and len(row) >= 4
        ],
        include_route_eta_by_fraction=pair_attention_input_dim > 0,
        n_route_eta_fractions=pair_attention_input_dim if pair_attention_input_dim > 0 else None,
        return_torch_tensors=False,
    )
    launch_mask = np_module.broadcast_to(output_tensors["launch_mask"], (batch_size, n_bodies))
    target_mask = np_module.broadcast_to(output_tensors["target_mask"], (batch_size, n_bodies, n_bodies))
    full_launch_mask = launch_mask
    full_target_mask = target_mask
    route_eta_input = None
    pair_attention_body_mask = None
    if pair_attention_input_dim > 0:
        route_eta_input = output_tensors["route_eta_by_fraction"][None, ...]
        pair_attention_body_mask = base_body_mask
    indices = body_indices(obs, n_bodies)
    full_fraction_mask = None
    if num_fleet_fractions > 0:
        full_fraction_mask = np_module.broadcast_to(
            build_target_fraction_mask(
                req,
                indices,
                n_bodies,
                num_fleet_fractions,
                output_tensors["target_mask"],
                output_tensors["launch_mask"],
                np_module,
            ),
            (batch_size, n_bodies, n_bodies, num_fleet_fractions),
        )
    if fixed_body_slots is None:
        x, body_mask, launch_mask, target_mask, active_indices = compact_body_inputs(
            x,
            body_mask,
            launch_mask,
            target_mask,
            np_module,
            reserved_prefix_slots=COMET_SLOTS,
        )
        if route_eta_input is not None:
            route_eta_input = route_eta_input[:, active_indices][:, :, active_indices, :]
        if pair_attention_body_mask is not None:
            pair_attention_body_mask = pair_attention_body_mask[:, active_indices]
    else:
        active_indices = np_module.arange(n_bodies, dtype=np_module.int64)
    return {
        "status": "OK",
        "id": request_id,
        "obs": obs,
        "n_bodies": n_bodies,
        "batch_size": batch_size,
        "x": x,
        "time_mask": time_mask,
        "body_mask": body_mask,
        "launch_mask": launch_mask,
        "target_mask": target_mask,
        "route_eta_by_fraction": route_eta_input,
        "pair_attention_body_mask": pair_attention_body_mask,
        "full_launch_mask": full_launch_mask,
        "full_target_mask": full_target_mask,
        "full_fraction_mask": full_fraction_mask,
        "active_indices": active_indices,
        "indices": indices,
    }


def decisions_from_outputs(
    prepared: dict[str, Any],
    launch_prob_compact: Any,
    target_logits_compact: Any,
    fraction_logits_compact: Any | None,
    num_fleet_fractions: int,
    np_module: Any,
) -> list[list[float | int | None]]:
    launch_prob, target_logits = scatter_compact_outputs(
        launch_prob_compact,
        target_logits_compact,
        prepared["active_indices"],
        prepared["n_bodies"],
        np_module,
    )
    fraction_logits = None
    if fraction_logits_compact is not None and num_fleet_fractions > 0:
        fraction_logits = scatter_compact_fraction_outputs(
            fraction_logits_compact,
            prepared["active_indices"],
            prepared["n_bodies"],
            num_fleet_fractions,
            np_module,
        )
    id_by_index = {idx: planet_id for planet_id, idx in prepared["indices"].items()}
    launch_mask_1d = np_module.asarray(prepared["full_launch_mask"][0], dtype=bool)
    target_mask_2d = np_module.asarray(prepared["full_target_mask"][0], dtype=bool)
    fraction_mask_3d = (
        np_module.asarray(prepared["full_fraction_mask"][0], dtype=bool)
        if prepared.get("full_fraction_mask") is not None
        else None
    )
    decisions: list[list[float | int | None]] = []
    for source_id, source_idx in sorted(prepared["indices"].items(), key=lambda item: item[1]):
        if source_idx < 0 or source_idx >= prepared["n_bodies"] or not bool(launch_mask_1d[source_idx]):
            continue
        target_id: int | None = None
        target_idx, target_prob = masked_softmax_argmax(
            target_logits[source_idx],
            target_mask_2d[source_idx],
            np_module,
        )
        if target_idx is not None:
            target_id = int(id_by_index.get(target_idx, -1))
        row: list[float | int | None] = [
            int(source_id),
            float(launch_prob[source_idx]),
            target_id,
            float(target_prob),
        ]
        if fraction_logits is not None and fraction_mask_3d is not None and target_idx is not None:
            fraction_idx, fraction_prob = masked_softmax_argmax(
                fraction_logits[source_idx],
                fraction_mask_3d[source_idx, target_idx],
                np_module,
            )
            row.extend([fraction_idx, float(fraction_prob)])
        decisions.append(row)
    return decisions


def predict_many(
    requests: list[dict[str, Any]],
    jax: Any,
    jnp: Any,
    model_fn: Any,
    fraction_head_fn: Any,
    params: Any,
    feature_mode: str,
    rotation_tta: bool,
    max_timesteps: int,
    fixed_body_slots: int | None,
    num_fleet_fractions: int,
    pair_attention_input_dim: int = 0,
    enemy_tta: bool = False,
) -> list[dict[str, Any]]:
    global FIRST_INFERENCE
    import numpy as np

    if not requests:
        return []

    max_batch_requests = max_batch_requests_from_env()
    if max_batch_requests is not None and len(requests) > max_batch_requests:
        responses: list[dict[str, Any]] = []
        for start in range(0, len(requests), max_batch_requests):
            responses.extend(
                predict_many(
                    requests[start : start + max_batch_requests],
                    jax,
                    jnp,
                    model_fn,
                    fraction_head_fn,
                    params,
                    feature_mode,
                    rotation_tta,
                    max_timesteps,
                    fixed_body_slots,
                    num_fleet_fractions,
                    pair_attention_input_dim,
                    enemy_tta=enemy_tta,
                )
            )
        return responses

    feature_started = time.perf_counter()
    prepared_rows: list[dict[str, Any]] = []
    responses: list[dict[str, Any] | None] = [None] * len(requests)
    for idx, req in enumerate(requests):
        try:
            prepared = prepare_request_inputs(
                req,
                np,
                feature_mode,
                rotation_tta,
                max_timesteps,
                fixed_body_slots,
                num_fleet_fractions,
                pair_attention_input_dim,
                enemy_tta=enemy_tta,
            )
        except Exception as exc:  # noqa: BLE001 - return row-level errors when possible.
            request_id = int(req.get("id", -1)) if isinstance(req, dict) else -1
            responses[idx] = {
                "status": "ERR",
                "id": request_id,
                "error": str(exc).replace("\n", " "),
            }
            continue
        if prepared.get("status") != "OK":
            responses[idx] = prepared
            continue
        prepared["response_index"] = idx
        prepared_rows.append(prepared)

    if not prepared_rows:
        return [response or {"status": "ERR", "id": -1, "error": "empty batch"} for response in responses]

    model_body_slots = int(prepared_rows[0]["x"].shape[1])
    batch_size_per_request = int(prepared_rows[0]["batch_size"])
    if any(int(row["x"].shape[1]) != model_body_slots for row in prepared_rows):
        if len(prepared_rows) > 1:
            raise RuntimeError("batched requests must share model body slot count")
    if any(int(row["batch_size"]) != batch_size_per_request for row in prepared_rows):
        raise RuntimeError("batched requests must share TTA batch size")
    view_tta = batch_size_per_request > 1

    padded_request_count = (
        next_power_of_two(len(prepared_rows)) if fixed_body_slots is not None else len(prepared_rows)
    )
    x_rows = [row["x"] for row in prepared_rows]
    time_rows = [row["time_mask"] for row in prepared_rows]
    body_rows = [row["body_mask"] for row in prepared_rows]
    launch_rows = [row["launch_mask"] for row in prepared_rows]
    target_rows = [row["target_mask"] for row in prepared_rows]
    route_eta_rows = (
        [row["route_eta_by_fraction"] for row in prepared_rows]
        if pair_attention_input_dim > 0
        else None
    )
    pair_attention_body_rows = (
        [row["pair_attention_body_mask"] for row in prepared_rows]
        if pair_attention_input_dim > 0
        else None
    )
    if padded_request_count > len(prepared_rows):
        pad_count = padded_request_count - len(prepared_rows)
        x_shape = prepared_rows[0]["x"].shape
        time_shape = prepared_rows[0]["time_mask"].shape
        body_shape = prepared_rows[0]["body_mask"].shape
        launch_shape = prepared_rows[0]["launch_mask"].shape
        target_shape = prepared_rows[0]["target_mask"].shape
        route_eta_shape = (
            prepared_rows[0]["route_eta_by_fraction"].shape
            if route_eta_rows is not None
            else None
        )
        pair_attention_body_shape = (
            prepared_rows[0]["pair_attention_body_mask"].shape
            if pair_attention_body_rows is not None
            else None
        )
        for _ in range(pad_count):
            x_rows.append(np.zeros(x_shape, dtype=np.float32))
            time_rows.append(np.zeros(time_shape, dtype=bool))
            body_rows.append(np.zeros(body_shape, dtype=bool))
            launch_rows.append(np.zeros(launch_shape, dtype=bool))
            target_rows.append(np.zeros(target_shape, dtype=bool))
            if route_eta_rows is not None and route_eta_shape is not None:
                route_eta_rows.append(np.zeros(route_eta_shape, dtype=np.float32))
            if pair_attention_body_rows is not None and pair_attention_body_shape is not None:
                pair_attention_body_rows.append(np.zeros(pair_attention_body_shape, dtype=bool))

    x = np.concatenate(x_rows, axis=0)
    time_mask = np.concatenate(time_rows, axis=0)
    body_mask = np.concatenate(body_rows, axis=0)
    launch_mask = np.concatenate(launch_rows, axis=0)
    target_mask = np.concatenate(target_rows, axis=0)
    route_eta_by_fraction = (
        np.concatenate(route_eta_rows, axis=0)
        if route_eta_rows is not None
        else None
    )
    pair_attention_body_mask = (
        np.concatenate(pair_attention_body_rows, axis=0)
        if pair_attention_body_rows is not None
        else None
    )
    inference_shape = (int(x.shape[0]), int(model_body_slots), int(time_mask.shape[1]))
    was_first_shape_inference = inference_shape not in SEEN_INFERENCE_SHAPES
    feature_done = time.perf_counter()

    nn_started = feature_done
    was_first_inference = FIRST_INFERENCE
    if was_first_inference or was_first_shape_inference:
        log_status(
            "compile_or_first_inference_start",
            request_id=prepared_rows[0]["id"],
            requests=len(prepared_rows),
            padded_requests=padded_request_count,
            model_batch_size=int(x.shape[0]),
            ensemble_members=len(model_param_sets(params)),
            body_slots=model_body_slots,
            timesteps=int(time_mask.shape[1]),
            first_process_call=was_first_inference,
            first_shape_call=was_first_shape_inference,
        )
    x_jax = jnp.asarray(x, dtype=jnp.bfloat16)
    time_mask_jax = jnp.asarray(time_mask)
    body_mask_jax = jnp.asarray(body_mask)
    launch_mask_jax = jnp.asarray(launch_mask)
    target_mask_jax = jnp.asarray(target_mask)
    route_eta_by_fraction_jax = (
        jnp.asarray(route_eta_by_fraction, dtype=jnp.float32)
        if route_eta_by_fraction is not None
        else None
    )
    pair_attention_body_mask_jax = (
        jnp.asarray(pair_attention_body_mask)
        if pair_attention_body_mask is not None
        else None
    )
    launch_logits_raw = None
    target_logits_raw = None
    param_sets = model_param_sets(params)
    hidden_states_by_member = []
    for member_params in param_sets:
        model_kwargs = {
            "time_mask": time_mask_jax,
            "body_mask": body_mask_jax,
            "launch_mask": launch_mask_jax,
            "target_mask": target_mask_jax,
        }
        if route_eta_by_fraction_jax is not None:
            model_kwargs["route_eta_by_fraction"] = route_eta_by_fraction_jax
            if (
                pair_attention_body_mask_jax is not None
                and int(route_eta_by_fraction_jax.shape[0]) != int(x_jax.shape[0])
            ):
                model_kwargs["pair_attention_body_mask"] = pair_attention_body_mask_jax
        out = model_fn(member_params, x_jax, **model_kwargs)
        member_launch_logits = out.launch_logits.astype(jnp.float32)
        member_target_logits = out.target_logits.astype(jnp.float32)
        if num_fleet_fractions > 0:
            hidden_states_by_member.append(out.hidden_states.astype(jnp.float32))
        if launch_logits_raw is None:
            launch_logits_raw = member_launch_logits
            target_logits_raw = member_target_logits
        else:
            launch_logits_raw = launch_logits_raw + member_launch_logits
            target_logits_raw = target_logits_raw + member_target_logits
    if len(param_sets) > 1:
        scale = np.float32(1.0 / len(param_sets))
        launch_logits_raw = launch_logits_raw * scale
        target_logits_raw = target_logits_raw * scale
    jax.block_until_ready((launch_logits_raw, target_logits_raw))
    if was_first_shape_inference:
        SEEN_INFERENCE_SHAPES.add(inference_shape)
    if was_first_inference:
        FIRST_INFERENCE = False
    if was_first_inference or was_first_shape_inference:
        log_status(
            "compile_or_first_inference_done",
            request_id=prepared_rows[0]["id"],
            requests=len(prepared_rows),
            padded_requests=padded_request_count,
            model_batch_size=int(x.shape[0]),
            ensemble_members=len(param_sets),
            body_slots=model_body_slots,
            timesteps=int(time_mask.shape[1]),
            first_process_call=was_first_inference,
            first_shape_call=was_first_shape_inference,
        )

    launch_logits = launch_logits_raw
    target_logits_jax = target_logits_raw
    if view_tta:
        launch_logits = launch_logits.reshape(
            (padded_request_count, batch_size_per_request, model_body_slots)
        )
        target_logits_jax = target_logits_jax.reshape(
            (padded_request_count, batch_size_per_request, model_body_slots, model_body_slots)
        )
        launch_logits = jnp.mean(launch_logits, axis=1)
        target_logits_jax = jnp.mean(target_logits_jax, axis=1)
    else:
        launch_logits = launch_logits.reshape((padded_request_count, model_body_slots))
        target_logits_jax = target_logits_jax.reshape(
            (padded_request_count, model_body_slots, model_body_slots)
        )
    fraction_logits_jax = None
    if num_fleet_fractions > 0 and hidden_states_by_member:
        fraction_target_index = jnp.argmax(target_logits_jax, axis=-1)
        if view_tta:
            raw_fraction_target_index = jnp.repeat(
                fraction_target_index,
                batch_size_per_request,
                axis=0,
            )
        else:
            raw_fraction_target_index = fraction_target_index
        for member_params, member_hidden_states in zip(param_sets, hidden_states_by_member):
            member_fraction_logits = fraction_head_fn(
                member_params,
                member_hidden_states,
                raw_fraction_target_index,
            ).astype(jnp.float32)
            if view_tta:
                member_fraction_logits = member_fraction_logits.reshape(
                    (
                        padded_request_count,
                        batch_size_per_request,
                        model_body_slots,
                        num_fleet_fractions,
                    )
                )
                member_fraction_logits = jnp.mean(member_fraction_logits, axis=1)
            else:
                member_fraction_logits = member_fraction_logits.reshape(
                    (padded_request_count, model_body_slots, num_fleet_fractions)
                )
            if fraction_logits_jax is None:
                fraction_logits_jax = member_fraction_logits
            else:
                fraction_logits_jax = fraction_logits_jax + member_fraction_logits
        if len(param_sets) > 1:
            fraction_logits_jax = fraction_logits_jax * np.float32(1.0 / len(param_sets))
    launch_prob_jax = jax.nn.sigmoid(launch_logits)
    if fraction_logits_jax is None:
        jax.block_until_ready((launch_prob_jax, target_logits_jax))
    else:
        jax.block_until_ready((launch_prob_jax, target_logits_jax, fraction_logits_jax))
    nn_done = time.perf_counter()
    nn_ms = (nn_done - nn_started) * 1000.0
    feature_ms = (feature_done - feature_started) * 1000.0

    if was_first_inference:
        log_status(
            "first_inference_summary",
            request_id=prepared_rows[0]["id"],
            requests=len(prepared_rows),
            padded_requests=padded_request_count,
            model_batch_size=int(x.shape[0]),
            body_slots=model_body_slots,
            timesteps=int(time_mask.shape[1]),
            import_jax_ms=f"{float(STARTUP_METRICS.get('import_jax_ms', 0.0)):.1f}",
            load_artifact_ms=f"{float(STARTUP_METRICS.get('load_artifact_ms', 0.0)):.1f}",
            ready_ms=f"{float(STARTUP_METRICS.get('ready_ms', 0.0)):.1f}",
            feature_ms=f"{feature_ms:.1f}",
            nn_ms=f"{nn_ms:.1f}",
            jax_version=STARTUP_METRICS.get("jax_version", "unknown"),
            backend=STARTUP_METRICS.get("backend", "unknown"),
            arrays=STARTUP_METRICS.get("arrays", "unknown"),
            ensemble_members=STARTUP_METRICS.get("ensemble_members", len(param_sets)),
            input_dim=STARTUP_METRICS.get("input_dim", "unknown"),
            pair_attention_input_dim=STARTUP_METRICS.get("pair_attention_input_dim", 0),
            rotation_tta=STARTUP_METRICS.get("rotation_tta", rotation_tta),
            enemy_tta=STARTUP_METRICS.get("enemy_tta", enemy_tta),
            max_timesteps=STARTUP_METRICS.get("max_timesteps", max_timesteps),
        )

    launch_prob_np = np.asarray(launch_prob_jax, dtype=np.float32)
    target_logits_np = np.asarray(target_logits_jax, dtype=np.float32)
    fraction_logits_np = (
        np.asarray(fraction_logits_jax, dtype=np.float32)
        if fraction_logits_jax is not None
        else None
    )
    for output_idx, prepared in enumerate(prepared_rows):
        response_index = int(prepared["response_index"])
        responses[response_index] = {
            "status": "OK",
            "id": int(prepared["id"]),
            "decisions": decisions_from_outputs(
                prepared,
                launch_prob_np[output_idx],
                target_logits_np[output_idx],
                fraction_logits_np[output_idx] if fraction_logits_np is not None else None,
                num_fleet_fractions,
                np,
            ),
        }

    if any(should_log_timing(int(row["id"]), rotation_tta) for row in prepared_rows):
        print(
            f"batch_requests={len(prepared_rows)} "
            f"padded_requests={padded_request_count} "
            f"feature_ms={feature_ms:.3f} "
            f"nn_ms={nn_ms:.3f}",
            file=sys.stderr,
            flush=True,
        )
    return [
        response or {"status": "ERR", "id": -1, "error": "missing batch response"}
        for response in responses
    ]


def predict_line(
    req: dict[str, Any],
    jax: Any,
    jnp: Any,
    model_fn: Any,
    fraction_head_fn: Any,
    params: Any,
    feature_mode: str,
    rotation_tta: bool,
    max_timesteps: int,
    fixed_body_slots: int | None,
    num_fleet_fractions: int,
    pair_attention_input_dim: int = 0,
    enemy_tta: bool = False,
) -> str:
    responses = predict_many(
        [req],
        jax,
        jnp,
        model_fn,
        fraction_head_fn,
        params,
        feature_mode,
        rotation_tta,
        max_timesteps,
        fixed_body_slots,
        num_fleet_fractions,
        pair_attention_input_dim,
        enemy_tta=enemy_tta,
    )
    return json.dumps(
        responses[0],
        separators=(",", ":"),
    )


def main() -> int:
    log_status("process_start", python=sys.version.split()[0], cwd=os.getcwd(), file=__file__)
    try:
        root = configure_imports()
        log_status("imports_configured", root=root)
        (
            jax,
            jnp,
            model_fn,
            fraction_head_fn,
            params,
            feature_mode,
            rotation_tta,
            enemy_tta,
            max_timesteps,
            fixed_body_slots,
            num_fleet_fractions,
            pair_attention_input_dim,
        ) = load_policy(root)
        log_status("ready")
    except Exception as exc:
        log_status("fatal", error=repr(exc), traceback=" | ".join(traceback.format_exc().splitlines()[-6:]))
        raise

    request_count = 0
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
            if isinstance(payload, dict) and isinstance(payload.get("batch"), list):
                requests = [req for req in payload["batch"] if isinstance(req, dict)]
                request_count += len(requests)
                rows = predict_many(
                    requests,
                    jax,
                    jnp,
                    model_fn,
                    fraction_head_fn,
                    params,
                    feature_mode,
                    rotation_tta,
                    max_timesteps,
                    fixed_body_slots,
                    num_fleet_fractions,
                    pair_attention_input_dim,
                    enemy_tta=enemy_tta,
                )
                response = json.dumps({"status": "OK", "batch": rows}, separators=(",", ":"))
                if request_count <= 3 or request_count % 50 == 0:
                    first_id = requests[0].get("id", -1) if requests else -1
                    log_status(
                        "inference_ok",
                        request_count=request_count,
                        request_id=first_id,
                        batch_requests=len(requests),
                    )
            else:
                request_count += 1
                response = predict_line(
                    payload,
                    jax,
                    jnp,
                    model_fn,
                    fraction_head_fn,
                    params,
                    feature_mode,
                    rotation_tta,
                    max_timesteps,
                    fixed_body_slots,
                    num_fleet_fractions,
                    pair_attention_input_dim,
                    enemy_tta=enemy_tta,
                )
                if request_count <= 3 or request_count % 50 == 0:
                    request_id = payload.get("id", -1) if isinstance(payload, dict) else -1
                    log_status("inference_ok", request_count=request_count, request_id=request_id)
        except Exception as exc:  # noqa: BLE001 - keep the Rust side alive on bad rows.
            request_id = -1
            try:
                request_id = int(json.loads(line).get("id", -1))
            except Exception:
                pass
            message = str(exc).replace("\t", " ").replace("\n", " ")
            log_status("inference_error", request_count=request_count, request_id=request_id, error=message)
            response = json.dumps(
                {"status": "ERR", "id": request_id, "error": message},
                separators=(",", ":"),
            )
        sys.stdout.write(response + "\n")
        sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
