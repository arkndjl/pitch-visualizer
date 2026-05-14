"""
Pitch Visualizer — Streamlit app for exploring MLB pitcher arsenals.

Run with:
    streamlit run pitch_visualizer.py

Search a pitcher by name, pick one or more seasons, then choose a chart:
movement, velocity distribution, or usage breakdown.

Data source: MLB Statcast via pybaseball.
"""

from __future__ import annotations

import datetime as dt
from typing import Optional

import matplotlib.pyplot as plt
import pandas as pd
import pybaseball as pyb
import streamlit as st
from pybaseball import playerid_lookup, statcast_pitcher

# Cache pybaseball requests to disk between runs
pyb.cache.enable()

# ────────────────────────────────────────────────────────────────────────────
# Pitch color + label maps. Colors match the Baseball Savant convention loosely
# so the charts read the way fans expect.
# ────────────────────────────────────────────────────────────────────────────
PITCH_COLORS: dict[str, str] = {
    "FF": "#E24B4A",  # Four-seam fastball
    "SI": "#E27D4A",  # Sinker
    "FT": "#E27D4A",  # Two-seam (legacy code, same color as sinker)
    "FC": "#BA7517",  # Cutter
    "SL": "#378ADD",  # Slider
    "ST": "#5BAFF5",  # Sweeper
    "SV": "#1E5A99",  # Slurve
    "CU": "#57068C",  # Curveball
    "KC": "#7E2CB5",  # Knuckle curve
    "CS": "#9B59B6",  # Slow curve
    "CH": "#1D9E75",  # Changeup
    "FS": "#639922",  # Splitter / ghost fork
    "FO": "#8FB339",  # Forkball
    "SC": "#C9A227",  # Screwball
    "KN": "#888780",  # Knuckleball
    "EP": "#555555",  # Eephus
    "PO": "#AAAAAA",  # Pitchout
}

PITCH_NAMES: dict[str, str] = {
    "FF": "Four-Seam",
    "SI": "Sinker",
    "FT": "Two-Seam",
    "FC": "Cutter",
    "SL": "Slider",
    "ST": "Sweeper",
    "SV": "Slurve",
    "CU": "Curveball",
    "KC": "Knuckle Curve",
    "CS": "Slow Curve",
    "CH": "Changeup",
    "FS": "Splitter",
    "FO": "Forkball",
    "SC": "Screwball",
    "KN": "Knuckleball",
    "EP": "Eephus",
    "PO": "Pitchout",
}


def label_for(pitch_code: str) -> str:
    """Return 'FF — Four-Seam' style label for a pitch code."""
    name = PITCH_NAMES.get(pitch_code, "Unknown")
    return f"{pitch_code} — {name}"


def color_for(pitch_code: str) -> str:
    """Return hex color for a pitch, defaulting to gray if unmapped."""
    return PITCH_COLORS.get(pitch_code, "#888888")


# ────────────────────────────────────────────────────────────────────────────
# Data fetching with Streamlit caching
# ────────────────────────────────────────────────────────────────────────────
@st.cache_data(show_spinner=False)
def search_pitchers(query: str) -> pd.DataFrame:
    """
    Look up players by name. pybaseball expects (last, first) but we'll be
    flexible: accept 'Gerrit Cole', 'Cole', or 'Cole, Gerrit'.
    """
    query = query.strip()
    if not query:
        return pd.DataFrame()

    if "," in query:
        last, first = [p.strip() for p in query.split(",", 1)]
    else:
        parts = query.split()
        if len(parts) == 1:
            last, first = parts[0], None
        else:
            # Treat last token as last name, the rest as first name
            last = parts[-1]
            first = " ".join(parts[:-1])

    try:
        df = playerid_lookup(last, first)
    except Exception:
        return pd.DataFrame()

    if df.empty:
        return df

    # Only keep players who have an MLBAM id (needed for Statcast)
    df = df.dropna(subset=["key_mlbam"])
    df = df[df["key_mlbam"] != 0]
    # Sort by most recent activity so current players surface first
    df = df.sort_values("mlb_played_last", ascending=False, na_position="last")
    return df.reset_index(drop=True)


@st.cache_data(show_spinner=False)
def fetch_pitcher_season(player_id: int, season: int) -> pd.DataFrame:
    """Pull a full season of Statcast pitch data for one pitcher."""
    start = f"{season}-03-15"  # Spring training cutoff — regular season starts late March
    end = f"{season}-11-15"  # Covers postseason
    try:
        df = statcast_pitcher(start, end, player_id=int(player_id))
    except Exception as e:
        st.error(f"Error fetching {season}: {e}")
        return pd.DataFrame()
    if df is None or df.empty:
        return pd.DataFrame()
    df["season"] = season
    return df


def fetch_pitcher_seasons(player_id: int, seasons: list[int]) -> pd.DataFrame:
    """Fetch multiple seasons and concat. Shows a progress bar."""
    frames = []
    progress = st.progress(0.0, text="Fetching Statcast data…")
    for i, season in enumerate(seasons, start=1):
        progress.progress(
            (i - 1) / len(seasons),
            text=f"Fetching {season} ({i}/{len(seasons)})…",
        )
        df = fetch_pitcher_season(player_id, season)
        if not df.empty:
            frames.append(df)
    progress.empty()
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


# ────────────────────────────────────────────────────────────────────────────
# Charting
# ────────────────────────────────────────────────────────────────────────────
def dominant_hand(df: pd.DataFrame) -> str:
    """
    Return 'R' or 'L' based on which the pitcher threw more.
    Almost every pitcher is exclusively one or the other; a handful (Pat
    Venditte) are switch pitchers, in which case we default to whichever
    hand they used more in the data.
    """
    if "p_throws" not in df.columns:
        return "R"
    counts = df["p_throws"].dropna().value_counts()
    if counts.empty:
        return "R"
    return str(counts.idxmax())


def chart_movement(df: pd.DataFrame, title: str) -> plt.Figure:
    """
    Horizontal vs vertical break, one cluster per pitch type.

    Statcast pfx_x is from the catcher's perspective: positive = toward the
    third-base side of the plate, negative = toward first base. To make
    "arm side" consistently appear on the RIGHT of the chart regardless of
    handedness, we flip the sign based on which hand the pitcher throws with:
      - RHP arm side is the first-base side (negative pfx_x) → flip sign
      - LHP arm side is the third-base side (positive pfx_x) → keep sign
    """
    fig, ax = plt.subplots(figsize=(10, 8), facecolor="white")
    sub = df.dropna(subset=["pfx_x", "pfx_z", "pitch_type"]).copy()

    hand = dominant_hand(sub)
    # Flip per-pitch so a switch pitcher's lefty pitches still land on
    # arm side relative to that pitch's handedness.
    if "p_throws" in sub.columns:
        sign = sub["p_throws"].map({"R": -1, "L": 1}).fillna(-1 if hand == "R" else 1)
    else:
        sign = -1 if hand == "R" else 1
    sub["h_break_in"] = sign * sub["pfx_x"] * 12
    sub["v_break_in"] = sub["pfx_z"] * 12

    pitch_order = sub["pitch_type"].value_counts().index.tolist()
    for pitch in pitch_order:
        pts = sub[sub["pitch_type"] == pitch]
        if len(pts) < 5:  # Skip tiny samples (data artifacts)
            continue
        ax.scatter(
            pts["h_break_in"],
            pts["v_break_in"],
            s=18,
            alpha=0.35,
            color=color_for(pitch),
            edgecolors="none",
            label=label_for(pitch),
        )
        # Centroid marker
        ax.scatter(
            pts["h_break_in"].mean(),
            pts["v_break_in"].mean(),
            marker="X",
            s=220,
            color=color_for(pitch),
            edgecolors="black",
            linewidths=1.5,
            zorder=5,
        )

    ax.axhline(0, color="#999", linewidth=0.8, linestyle="--")
    ax.axvline(0, color="#999", linewidth=0.8, linestyle="--")

    hand_label = {"R": "RHP", "L": "LHP"}.get(hand, "RHP")
    ax.set_xlabel(
        f"Horizontal break (inches) — ← glove side | arm side → ({hand_label}, pitcher's POV)",
        fontsize=10,
    )
    ax.set_ylabel("Vertical break (inches)", fontsize=11)
    ax.set_title(title, fontsize=14, weight="bold", pad=14)
    ax.legend(loc="best", fontsize=9, framealpha=0.95)
    ax.grid(True, alpha=0.25)
    ax.set_aspect("equal", adjustable="datalim")
    fig.tight_layout()
    return fig


def chart_velocity(df: pd.DataFrame, title: str) -> plt.Figure:
    """Velocity distribution per pitch type as overlapping density-ish histograms."""
    fig, ax = plt.subplots(figsize=(10, 6), facecolor="white")
    sub = df.dropna(subset=["release_speed", "pitch_type"])
    pitch_order = sub["pitch_type"].value_counts().index.tolist()

    for pitch in pitch_order:
        speeds = sub.loc[sub["pitch_type"] == pitch, "release_speed"]
        if len(speeds) < 5:
            continue
        ax.hist(
            speeds,
            bins=30,
            alpha=0.55,
            color=color_for(pitch),
            label=f"{label_for(pitch)} (avg {speeds.mean():.1f})",
            edgecolor="white",
            linewidth=0.5,
        )

    ax.set_xlabel("Release velocity (mph)", fontsize=11)
    ax.set_ylabel("Pitch count", fontsize=11)
    ax.set_title(title, fontsize=14, weight="bold", pad=14)
    ax.legend(loc="best", fontsize=9, framealpha=0.95)
    ax.grid(True, alpha=0.25, axis="y")
    fig.tight_layout()
    return fig


def chart_usage(df: pd.DataFrame, title: str) -> plt.Figure:
    """Pitch usage breakdown as a horizontal bar chart with counts and percentages."""
    fig, ax = plt.subplots(figsize=(10, 6), facecolor="white")
    sub = df.dropna(subset=["pitch_type"])
    counts = sub["pitch_type"].value_counts()
    total = counts.sum()
    pct = (counts / total * 100).round(1)

    labels = [label_for(p) for p in counts.index]
    colors = [color_for(p) for p in counts.index]
    y_pos = range(len(counts))[::-1]  # Largest at top

    bars = ax.barh(list(y_pos), counts.values, color=colors, edgecolor="black", linewidth=0.5)
    ax.set_yticks(list(y_pos))
    ax.set_yticklabels(labels, fontsize=10)
    ax.set_xlabel("Pitch count", fontsize=11)
    ax.set_title(title, fontsize=14, weight="bold", pad=14)
    ax.grid(True, alpha=0.25, axis="x")

    # Annotate with count + percentage
    for bar, count, p in zip(bars, counts.values, pct.values):
        ax.text(
            bar.get_width() + total * 0.005,
            bar.get_y() + bar.get_height() / 2,
            f"{count}  ({p}%)",
            va="center",
            fontsize=9,
        )

    ax.set_xlim(0, counts.max() * 1.15)
    fig.tight_layout()
    return fig


def build_summary_table(df: pd.DataFrame) -> pd.DataFrame:
    """Per-pitch summary: count, %, avg velo, avg spin, avg movement.

    H-break is flipped per pitch using p_throws so positive = arm side for
    both RHP and LHP, matching the movement chart convention.
    """
    sub = df.dropna(subset=["pitch_type"]).copy()
    if "p_throws" in sub.columns:
        sign = sub["p_throws"].map({"R": -1, "L": 1}).fillna(-1)
    else:
        sign = -1
    sub["h_break_signed"] = sign * sub["pfx_x"]

    grouped = sub.groupby("pitch_type").agg(
        Count=("pitch_type", "count"),
        Avg_Velo=("release_speed", "mean"),
        Avg_Spin=("release_spin_rate", "mean"),
        Avg_HBreak_in=("h_break_signed", lambda s: s.mean() * 12),
        Avg_VBreak_in=("pfx_z", lambda s: s.mean() * 12),
    )
    grouped["Usage_%"] = (grouped["Count"] / grouped["Count"].sum() * 100).round(1)
    grouped = grouped.round(1)
    grouped["Pitch"] = [label_for(p) for p in grouped.index]
    grouped = grouped[["Pitch", "Count", "Usage_%", "Avg_Velo", "Avg_Spin", "Avg_HBreak_in", "Avg_VBreak_in"]]
    grouped = grouped.sort_values("Count", ascending=False).reset_index(drop=True)
    return grouped


# ────────────────────────────────────────────────────────────────────────────
# Streamlit UI
# ────────────────────────────────────────────────────────────────────────────
def main() -> None:
    st.set_page_config(page_title="Pitch Visualizer", page_icon="⚾", layout="wide")
    st.title("⚾ Pitch Visualizer")
    st.caption("Statcast-powered pitch arsenal explorer. Data via pybaseball.")

    # ── Step 1: Find a pitcher ─────────────────────────────────────────────
    st.subheader("1. Find a pitcher")
    name_query = st.text_input(
        "Pitcher name",
        placeholder="e.g. Gerrit Cole, Kodai Senga, Snell",
        help="Full name, last name, or 'Last, First' all work.",
    )

    if not name_query:
        st.info("Enter a pitcher's name above to begin.")
        return

    matches = search_pitchers(name_query)
    if matches.empty:
        st.warning("No matching players found. Check spelling or try just the last name.")
        return

    # Build labels: "Gerrit Cole (2013–2025)"
    def fmt_match(idx: int) -> str:
        row = matches.iloc[idx]
        first = row.get("name_first", "") or ""
        last = row.get("name_last", "") or ""
        first_yr = row.get("mlb_played_first")
        last_yr = row.get("mlb_played_last")
        career = ""
        if pd.notna(first_yr) and pd.notna(last_yr):
            career = f" ({int(first_yr)}–{int(last_yr)})"
        return f"{first.title()} {last.title()}{career}"

    options = list(range(len(matches)))
    selected_idx = st.selectbox(
        f"Select pitcher ({len(matches)} match{'es' if len(matches) != 1 else ''})",
        options=options,
        format_func=fmt_match,
    )
    selected = matches.iloc[selected_idx]
    player_id = int(selected["key_mlbam"])
    player_name = f"{selected['name_first'].title()} {selected['name_last'].title()}"

    # ── Step 2: Pick seasons ───────────────────────────────────────────────
    st.subheader("2. Choose seasons")
    first_yr = selected.get("mlb_played_first")
    last_yr = selected.get("mlb_played_last")
    current_year = dt.date.today().year

    if pd.isna(first_yr) or pd.isna(last_yr):
        st.warning("No MLB seasons on record for this player.")
        return

    # Statcast era starts in 2015 — older seasons exist but won't have pitch tracking
    statcast_start = max(int(first_yr), 2015)
    statcast_end = min(int(last_yr), current_year)
    if statcast_start > statcast_end:
        st.warning(
            f"This player's MLB career ({int(first_yr)}–{int(last_yr)}) predates the "
            "Statcast era (2015+). No pitch-tracking data available."
        )
        return

    available_seasons = list(range(statcast_end, statcast_start - 1, -1))
    seasons = st.multiselect(
        "Seasons (Statcast era only — 2015 onward)",
        options=available_seasons,
        default=[available_seasons[0]],
    )

    if not seasons:
        st.info("Pick at least one season to continue.")
        return

    # ── Step 3: Chart picker ───────────────────────────────────────────────
    st.subheader("3. Choose a visualization")
    chart_choice = st.radio(
        "Chart",
        options=[
            "Pitch movement",
            "Velocity distribution",
            "Usage breakdown",
            "All three",
        ],
        horizontal=True,
    )

    if not st.button("Generate", type="primary"):
        return

    # ── Fetch ──────────────────────────────────────────────────────────────
    with st.spinner(f"Loading {player_name} data…"):
        df = fetch_pitcher_seasons(player_id, sorted(seasons))

    if df.empty:
        st.error("No Statcast pitch data returned for that selection.")
        return

    pitch_count = len(df)
    season_str = ", ".join(str(s) for s in sorted(seasons))
    st.success(f"Loaded {pitch_count:,} pitches from {player_name} — {season_str}.")

    # ── Render ─────────────────────────────────────────────────────────────
    title_base = f"{player_name} — {season_str}"

    if chart_choice in ("Pitch movement", "All three"):
        st.markdown("### Pitch movement")
        st.caption("Each dot is one pitch. X marks each pitch type's cluster centroid. Catcher's view.")
        st.pyplot(chart_movement(df, f"{title_base} — Pitch Movement"))

    if chart_choice in ("Velocity distribution", "All three"):
        st.markdown("### Velocity distribution")
        st.caption("Overlapping histograms of release velocity per pitch type.")
        st.pyplot(chart_velocity(df, f"{title_base} — Velocity Distribution"))

    if chart_choice in ("Usage breakdown", "All three"):
        st.markdown("### Usage breakdown")
        st.caption("Pitch counts and share of total pitches thrown.")
        st.pyplot(chart_usage(df, f"{title_base} — Pitch Usage"))

    # ── Summary table ──────────────────────────────────────────────────────
    st.markdown("### Arsenal summary")
    summary = build_summary_table(df)
    st.dataframe(summary, hide_index=True, use_container_width=True)

    # ── CSV download ───────────────────────────────────────────────────────
    csv = summary.to_csv(index=False).encode("utf-8")
    fname = f"{player_name.replace(' ', '_').lower()}_{season_str.replace(', ', '_')}_summary.csv"
    st.download_button("Download summary CSV", csv, file_name=fname, mime="text/csv")


if __name__ == "__main__":
    main()
