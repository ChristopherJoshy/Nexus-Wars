from __future__ import annotations

from pathlib import Path
from typing import Mapping, NamedTuple

import jax
import jax.numpy as jnp
import numpy as np


NORM_EPS = 1.0e-5
ROPE_THETA = 10000.0

ParamMap = Mapping[str, jax.Array | np.ndarray]


class PlanetTransformerOutput(NamedTuple):
    launch_logits: jax.Array
    target_logits: jax.Array
    hidden_states: jax.Array
    fraction_logits: jax.Array | None = None


def load_params(path: str | Path) -> dict[str, jax.Array]:
    with np.load(path) as npz:
        return {key: jnp.asarray(npz[key]) for key in npz.files}


def linear(x: jax.Array, weight: jax.Array, bias: jax.Array | None = None) -> jax.Array:
    y = jnp.matmul(x, jnp.swapaxes(weight, -1, -2))
    if bias is not None:
        y = y + bias
    return y


def layer_norm(
    x: jax.Array,
    weight: jax.Array,
    bias: jax.Array | None = None,
    eps: float = NORM_EPS,
) -> jax.Array:
    x = x.astype(jnp.float32)
    mean = jnp.mean(x, axis=-1, keepdims=True)
    var = jnp.mean(jnp.square(x - mean), axis=-1, keepdims=True)
    y = (x - mean) * jax.lax.rsqrt(var + eps)
    y = y * weight
    if bias is not None:
        y = y + bias
    return y


def gelu(x: jax.Array) -> jax.Array:
    return jax.nn.gelu(x, approximate=False)


def conv1d_nct(x: jax.Array, weight: jax.Array, bias: jax.Array, padding: int) -> jax.Array:
    y = jax.lax.conv_general_dilated(
        x,
        weight,
        window_strides=(1,),
        padding=((padding, padding),),
        dimension_numbers=("NCT", "OIT", "NCT"),
    )
    return y + bias[None, :, None]


def conv_padding(weight: jax.Array) -> int:
    return int(weight.shape[-1]) // 2


def conv_block(params: ParamMap, prefix: str, x: jax.Array, residual_conv: bool) -> jax.Array:
    residual = x
    if residual_conv:
        residual_weight = params[f"{prefix}.residual.weight"]
        residual = conv1d_nct(
            x,
            residual_weight,
            params[f"{prefix}.residual.bias"],
            padding=conv_padding(residual_weight),
        )
    conv_weight = params[f"{prefix}.conv1d.weight"]
    y = conv1d_nct(
        x,
        conv_weight,
        params[f"{prefix}.conv1d.bias"],
        padding=conv_padding(conv_weight),
    )
    y = gelu(y) + residual
    y = jnp.swapaxes(y, 1, 2)
    y = layer_norm(
        y,
        params[f"{prefix}.layer_norm.weight"],
        params[f"{prefix}.layer_norm.bias"],
    )
    return jnp.swapaxes(y, 1, 2)


def num_conv_blocks(params: ParamMap) -> int:
    return sum(
        1
        for key in params
        if key.startswith("planet_embedding.conv_blocks.") and key.endswith(".conv1d.weight")
    )


def planet_embedding(
    params: ParamMap,
    x: jax.Array,
    *,
    time_mask: jax.Array,
    body_mask: jax.Array,
) -> jax.Array:
    batch_size, n_bodies, n_timesteps, input_dim = x.shape
    expected_input_dim = int(params["planet_embedding.conv_blocks.0.conv1d.weight"].shape[1])
    feature_dim = int(params["planet_embedding.conv_blocks.0.conv1d.weight"].shape[0])
    if input_dim != expected_input_dim:
        raise ValueError(f"expected input_dim={expected_input_dim}, got {input_dim}")

    x = x.astype(jnp.float32)
    valid = time_mask.astype(jnp.float32)
    if valid.ndim == 2:
        valid = jnp.broadcast_to(valid[:, None, :], (batch_size, n_bodies, n_timesteps))
    valid = valid * body_mask.astype(jnp.float32)[:, :, None]
    first_timestep = x[:, :, 0, :] * valid[:, :, 0, None]

    y = x * valid[:, :, :, None]
    y = y.reshape(batch_size * n_bodies, n_timesteps, input_dim)
    y = jnp.swapaxes(y, 1, 2)
    block_mask = valid.reshape(batch_size * n_bodies, n_timesteps)[:, None, :]
    for idx in range(num_conv_blocks(params)):
        y = conv_block(
            params,
            f"planet_embedding.conv_blocks.{idx}",
            y,
            residual_conv=idx == 0,
        )
        y = y * block_mask
    y = jnp.swapaxes(y, 1, 2).reshape(batch_size, n_bodies, n_timesteps, feature_dim)

    valid4 = valid[:, :, :, None]
    denom = jnp.maximum(jnp.sum(valid4, axis=2), 1.0)
    embeddings = jnp.sum(y * valid4, axis=2) / denom
    output_input_dim = int(params["planet_embedding.output.weight"].shape[1])
    if output_input_dim == feature_dim + input_dim:
        embeddings = jnp.concatenate([embeddings, first_timestep], axis=-1)
    elif output_input_dim != feature_dim:
        raise ValueError(f"unexpected planet embedding output input dim={output_input_dim}")
    embeddings = linear(
        embeddings,
        params["planet_embedding.output.weight"],
        params["planet_embedding.output.bias"],
    )
    return embeddings * body_mask.astype(jnp.float32)[:, :, None]


def rotate_half(x: jax.Array) -> jax.Array:
    x1 = x[..., : x.shape[-1] // 2]
    x2 = x[..., x.shape[-1] // 2 :]
    return jnp.concatenate([-x2, x1], axis=-1)


def rotary_embeddings(
    x: jax.Array,
    position_ids: jax.Array,
    *,
    head_dim: int,
) -> tuple[jax.Array, jax.Array]:
    inv_freq = 1.0 / (ROPE_THETA ** (jnp.arange(0, head_dim, 2, dtype=jnp.float32) / head_dim))
    freqs = position_ids.astype(jnp.float32)[:, :, None] * inv_freq[None, None, :]
    emb = jnp.concatenate([freqs, freqs], axis=-1)
    return jnp.cos(emb).astype(x.dtype), jnp.sin(emb).astype(x.dtype)


def apply_rotary_pos_emb(
    q: jax.Array,
    k: jax.Array,
    cos: jax.Array,
    sin: jax.Array,
) -> tuple[jax.Array, jax.Array]:
    cos = cos[:, None, :, :]
    sin = sin[:, None, :, :]
    qf = q.astype(jnp.float32)
    kf = k.astype(jnp.float32)
    q_embed = (qf * cos) + (rotate_half(qf) * sin)
    k_embed = (kf * cos) + (rotate_half(kf) * sin)
    return q_embed.astype(q.dtype), k_embed.astype(k.dtype)


def attention(
    params: ParamMap,
    prefix: str,
    hidden_states: jax.Array,
    *,
    position_embeddings: tuple[jax.Array, jax.Array],
    attention_mask: jax.Array | None = None,
    num_heads: int,
    head_dim: int,
) -> jax.Array:
    batch_size, seq_len, hidden_size = hidden_states.shape
    qkv = linear(hidden_states, params[f"{prefix}.Wqkv.weight"])
    qkv = qkv.reshape(batch_size, seq_len, 3, num_heads, head_dim)
    q = jnp.swapaxes(qkv[:, :, 0, :, :], 1, 2)
    k = jnp.swapaxes(qkv[:, :, 1, :, :], 1, 2)
    v = jnp.swapaxes(qkv[:, :, 2, :, :], 1, 2)
    q, k = apply_rotary_pos_emb(q, k, *position_embeddings)

    attn_weights = jnp.matmul(q, jnp.swapaxes(k, -1, -2)) * (head_dim**-0.5)
    if attention_mask is not None:
        attn_weights = attn_weights + attention_mask
    attn_weights = jax.nn.softmax(attn_weights.astype(jnp.float32), axis=-1).astype(q.dtype)
    attn_output = jnp.matmul(attn_weights, v)
    attn_output = jnp.swapaxes(attn_output, 1, 2).reshape(batch_size, seq_len, hidden_size)
    return linear(attn_output, params[f"{prefix}.Wo.weight"])


def mlp(params: ParamMap, prefix: str, hidden_states: jax.Array) -> jax.Array:
    wi = linear(hidden_states, params[f"{prefix}.Wi.weight"])
    inputs, gate = jnp.split(wi, 2, axis=-1)
    return linear(gelu(inputs) * gate, params[f"{prefix}.Wo.weight"])


def encoder_layer(
    params: ParamMap,
    layer_idx: int,
    hidden_states: jax.Array,
    *,
    attention_mask: jax.Array | None,
    position_embeddings: tuple[jax.Array, jax.Array],
    num_heads: int,
    head_dim: int,
) -> jax.Array:
    prefix = f"encoder.layers.{layer_idx}"
    attn_input = hidden_states
    if layer_idx != 0:
        attn_input = layer_norm(attn_input, params[f"{prefix}.attn_norm.weight"])
    hidden_states = hidden_states + attention(
        params,
        f"{prefix}.attn",
        attn_input,
        position_embeddings=position_embeddings,
        attention_mask=attention_mask,
        num_heads=num_heads,
        head_dim=head_dim,
    )
    hidden_states = hidden_states + mlp(
        params,
        f"{prefix}.mlp",
        layer_norm(hidden_states, params[f"{prefix}.mlp_norm.weight"]),
    )
    return hidden_states


def num_encoder_layers(params: ParamMap) -> int:
    return sum(
        1
        for key in params
        if key.startswith("encoder.layers.") and key.endswith(".attn.Wqkv.weight")
    )


def encoder(
    params: ParamMap,
    *,
    inputs_embeds: jax.Array,
    attention_mask: jax.Array | None = None,
    attention_biases: tuple[jax.Array, ...] | None = None,
    position_ids: jax.Array | None = None,
    num_heads: int,
    head_dim: int,
) -> jax.Array:
    batch_size, seq_len, _ = inputs_embeds.shape
    if position_ids is None:
        position_ids = jnp.broadcast_to(jnp.arange(seq_len)[None, :], (batch_size, seq_len))

    hidden_states = layer_norm(inputs_embeds, params["encoder.embeddings.norm.weight"])
    additive_mask = None
    if attention_mask is not None:
        valid = attention_mask.astype(bool)
        additive_mask = jnp.zeros((batch_size, 1, 1, seq_len), dtype=hidden_states.dtype)
        additive_mask = jnp.where(valid[:, None, None, :], additive_mask, jnp.finfo(hidden_states.dtype).min)

    position_embeddings = rotary_embeddings(hidden_states, position_ids, head_dim=head_dim)
    for layer_idx in range(num_encoder_layers(params)):
        layer_attention_mask = additive_mask
        if attention_biases is not None:
            layer_attention_bias = attention_biases[layer_idx]
            layer_attention_mask = (
                layer_attention_bias
                if layer_attention_mask is None
                else layer_attention_mask + layer_attention_bias
            )
        hidden_states = encoder_layer(
            params,
            layer_idx,
            hidden_states,
            attention_mask=layer_attention_mask,
            position_embeddings=position_embeddings,
            num_heads=num_heads,
            head_dim=head_dim,
        )
    return layer_norm(hidden_states, params["encoder.final_norm.weight"])


def target_attention(
    params: ParamMap,
    hidden_states: jax.Array,
    *,
    body_mask: jax.Array | None = None,
    num_heads: int,
    head_dim: int,
) -> jax.Array:
    batch_size, n_bodies, _ = hidden_states.shape
    q = linear(hidden_states, params["target_head.query.weight"])
    k = linear(hidden_states, params["target_head.key.weight"])
    q = jnp.swapaxes(q.reshape(batch_size, n_bodies, num_heads, head_dim), 1, 2)
    k = jnp.swapaxes(k.reshape(batch_size, n_bodies, num_heads, head_dim), 1, 2)
    scores = jnp.matmul(q, jnp.swapaxes(k, -1, -2)) / np.float32(head_dim**0.5)
    head_weights = jax.nn.softmax(params["target_head.head_weights"], axis=0).reshape(1, num_heads, 1, 1)
    logits = jnp.sum(scores * head_weights, axis=1)
    if body_mask is not None:
        valid = body_mask.astype(bool)
        pair_mask = valid[:, :, None] & valid[:, None, :]
        logits = jnp.where(pair_mask, logits, jnp.finfo(logits.dtype).min)
    return logits


def has_pair_attention_bias(params: ParamMap) -> bool:
    return (
        "pair_attention_bias.encoder.0.weight" in params
        and "pair_attention_bias.encoder.3.weight" in params
        and "pair_attention_bias.norm.weight" in params
    )


def num_pair_attention_layers(params: ParamMap) -> int:
    return sum(
        1
        for key in params
        if key.startswith("pair_attention_bias.layer_biases.") and key.endswith(".weight")
    )


def pair_attention_bias(
    params: ParamMap,
    raw_pair: jax.Array,
    *,
    body_mask: jax.Array | None,
) -> tuple[jax.Array, ...]:
    pair = raw_pair.astype(jnp.float32)
    pair = gelu(
        linear(
            pair,
            params["pair_attention_bias.encoder.0.weight"],
            params["pair_attention_bias.encoder.0.bias"],
        )
    )
    pair = gelu(
        linear(
            pair,
            params["pair_attention_bias.encoder.3.weight"],
            params["pair_attention_bias.encoder.3.bias"],
        )
    )
    pair = layer_norm(
        pair,
        params["pair_attention_bias.norm.weight"],
        params["pair_attention_bias.norm.bias"],
    )

    pair_mask = None
    if body_mask is not None:
        valid = body_mask.astype(bool)
        pair_mask = valid[:, None, :, None] & valid[:, None, None, :]

    biases = []
    for layer_idx in range(num_pair_attention_layers(params)):
        bias = linear(
            pair,
            params[f"pair_attention_bias.layer_biases.{layer_idx}.weight"],
            params[f"pair_attention_bias.layer_biases.{layer_idx}.bias"],
        )
        bias = jnp.transpose(bias, (0, 3, 1, 2))
        if pair_mask is not None:
            bias = jnp.where(pair_mask, bias, jnp.zeros_like(bias))
        biases.append(bias)
    return tuple(biases)


def repeat_attention_biases(
    biases: tuple[jax.Array, ...],
    *,
    target_batch_size: int,
) -> tuple[jax.Array, ...]:
    if not biases:
        return biases
    bias_batch_size = int(biases[0].shape[0])
    if bias_batch_size == target_batch_size:
        return biases
    if bias_batch_size <= 0 or target_batch_size % bias_batch_size != 0:
        raise ValueError(
            f"cannot broadcast pair attention batch {bias_batch_size} to {target_batch_size}"
        )
    repeats = target_batch_size // bias_batch_size
    return tuple(jnp.repeat(bias, repeats, axis=0) for bias in biases)


def has_fraction_head(params: ParamMap) -> bool:
    return "fraction_head.mlp.0.weight" in params and "fraction_head.mlp.2.weight" in params


def fraction_head(
    params: ParamMap,
    hidden_states: jax.Array,
    target_index: jax.Array,
    *,
    fraction_mask: jax.Array | None = None,
) -> jax.Array:
    batch_size, n_bodies, hidden_size = hidden_states.shape
    safe_target_index = jnp.clip(target_index.astype(jnp.int32), 0, n_bodies - 1)
    batch_index = jnp.arange(batch_size, dtype=jnp.int32)[:, None]
    target_hidden = hidden_states[batch_index, safe_target_index, :]
    y = jnp.concatenate([hidden_states, target_hidden], axis=-1)
    y = gelu(
        linear(
            y,
            params["fraction_head.mlp.0.weight"],
            params["fraction_head.mlp.0.bias"],
        )
    )
    logits = linear(
        y,
        params["fraction_head.mlp.2.weight"],
        params["fraction_head.mlp.2.bias"],
    )
    if fraction_mask is not None:
        logits = jnp.where(
            fraction_mask.astype(bool),
            logits,
            jnp.finfo(logits.dtype).min,
        )
    return logits


def planet_transformer(
    params: ParamMap,
    x: jax.Array,
    *,
    time_mask: jax.Array,
    body_mask: jax.Array,
    launch_mask: jax.Array | None = None,
    target_mask: jax.Array | None = None,
    fraction_target_index: jax.Array | None = None,
    fraction_mask: jax.Array | None = None,
    route_eta_by_fraction: jax.Array | None = None,
    pair_attention_body_mask: jax.Array | None = None,
) -> PlanetTransformerOutput:
    hidden_size = int(params["encoder.layers.0.attn.Wqkv.weight"].shape[1])
    num_heads = int(params["target_head.head_weights"].shape[0])
    head_dim = hidden_size // num_heads
    embeddings = planet_embedding(params, x, time_mask=time_mask, body_mask=body_mask)
    attention_mask = body_mask.astype(jnp.int32)
    position_ids = jnp.zeros((embeddings.shape[0], embeddings.shape[1]), dtype=jnp.int32)
    attention_biases = None
    if has_pair_attention_bias(params):
        if route_eta_by_fraction is None:
            raise ValueError("route_eta_by_fraction is required when pair attention is enabled")
        pair_body_mask = body_mask if pair_attention_body_mask is None else pair_attention_body_mask
        attention_biases = pair_attention_bias(
            params,
            route_eta_by_fraction,
            body_mask=pair_body_mask,
        )
        attention_biases = repeat_attention_biases(
            attention_biases,
            target_batch_size=int(embeddings.shape[0]),
        )
    hidden_states = encoder(
        params,
        inputs_embeds=embeddings,
        attention_mask=attention_mask,
        attention_biases=attention_biases,
        position_ids=position_ids,
        num_heads=num_heads,
        head_dim=head_dim,
    )
    hidden_states = hidden_states * body_mask.astype(hidden_states.dtype)[:, :, None]
    launch_logits = linear(
        hidden_states,
        params["launch_head.weight"],
        params["launch_head.bias"],
    ).squeeze(-1)
    valid_launch = body_mask if launch_mask is None else launch_mask
    launch_logits = jnp.where(
        valid_launch.astype(bool),
        launch_logits,
        jnp.finfo(launch_logits.dtype).min,
    )
    target_logits = target_attention(
        params,
        hidden_states,
        body_mask=body_mask,
        num_heads=num_heads,
        head_dim=head_dim,
    )
    if target_mask is not None:
        target_logits = jnp.where(
            target_mask.astype(bool),
            target_logits,
            jnp.finfo(target_logits.dtype).min,
        )
    fraction_logits = None
    if has_fraction_head(params):
        if fraction_target_index is None:
            fraction_target_index = jnp.argmax(target_logits, axis=-1)
        fraction_logits = fraction_head(
            params,
            hidden_states,
            fraction_target_index,
            fraction_mask=fraction_mask,
        )
    return PlanetTransformerOutput(
        launch_logits=launch_logits,
        target_logits=target_logits,
        hidden_states=hidden_states,
        fraction_logits=fraction_logits,
    )


jitted_planet_transformer = jax.jit(planet_transformer)
jitted_fraction_head = jax.jit(fraction_head)
