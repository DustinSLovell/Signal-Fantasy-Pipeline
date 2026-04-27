"""
validate_pitcher_calcs.py
Compares Statcast-derived ERA, FIP, and IP in pitcher_luck_input.csv against
official figures from the MLB Stats API (statsapi.mlb.com).

MLB Stats API returns:
  - inningsPitched  : baseball notation string, e.g. "9.2" = 9⅔ innings
  - outs            : raw out count (integer)
  - era             : official ERA (string, may be "-.--" for 0 ER)
  - earnedRuns      : integer
  - homeRuns, baseOnBalls, hitByPitch, strikeOuts : for FIP validation

Output:
  1. Top 20 by official IP — side-by-side comparison table
  2. Summary statistics (mean / max absolute difference) for ERA, IP, and FIP
"""

import os
import requests
import unicodedata
import pandas as pd

BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
INPUT_PATH = os.path.join(BASE_DIR, "pitcher_luck_input.csv")

MLB_API_URL = (
    "https://statsapi.mlb.com/api/v1/stats"
    "?stats=season&group=pitching&season=2026&gameType=R"
    "&limit=2000&offset=0&playerPool=ALL"
)

# FIP constant — same value used in process_pitcher_stats.py
LG_ERA = 4.00

MIN_IP_DISPLAY = 10.0   # official decimal IP


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def baseball_ip_to_decimal(ip_str: str) -> float:
    """
    Convert baseball-notation IP string to decimal innings.
    '9.2' → 9 + 2/3 = 9.667   |   '0.1' → 0.333   |   '27.0' → 27.0
    The digits after the decimal are OUTS (0, 1, or 2), not tenths.
    """
    try:
        whole, frac = str(ip_str).split(".")
        return int(whole) + int(frac) / 3
    except (ValueError, AttributeError):
        return float("nan")


def normalize_name(name: str) -> str:
    """Strip accents, lower-case, collapse whitespace for fuzzy joining."""
    if not isinstance(name, str):
        return ""
    nfkd = unicodedata.normalize("NFKD", name)
    ascii_str = "".join(c for c in nfkd if not unicodedata.combining(c))
    return " ".join(ascii_str.lower().split())


# ---------------------------------------------------------------------------
# Fetch MLB Stats API
# ---------------------------------------------------------------------------

def fetch_mlb_stats() -> pd.DataFrame:
    print("Fetching official stats from MLB Stats API …")
    r = requests.get(MLB_API_URL, timeout=20)
    r.raise_for_status()
    splits = r.json()["stats"][0]["splits"]
    print(f"  Pitchers returned: {len(splits):,}")

    rows = []
    for s in splits:
        stat = s["stat"]
        ip_str = stat.get("inningsPitched", "0.0")
        outs   = int(stat.get("outs", 0))
        er     = int(stat.get("earnedRuns", 0))
        hr     = int(stat.get("homeRuns", 0))
        bb     = int(stat.get("baseOnBalls", 0))
        hbp    = int(stat.get("hitByPitch", 0))
        k      = int(stat.get("strikeOuts", 0))
        era_raw = stat.get("era", "")

        ip_dec = outs / 3  # most reliable; avoids parsing edge cases

        # Official ERA (may be "-.--" when ER=0)
        try:
            era_official = float(era_raw)
        except (ValueError, TypeError):
            era_official = (er / ip_dec * 9) if ip_dec > 0 else 0.0

        rows.append({
            "name_mlb":    s["player"]["fullName"],
            "ip_official": round(ip_dec, 2),
            "era_official": round(era_official, 2),
            "er_official":  er,
            "hr_official":  hr,
            "bb_official":  bb,
            "hbp_official": hbp,
            "k_official":   k,
        })

    df = pd.DataFrame(rows)
    df["_key"] = df["name_mlb"].apply(normalize_name)
    return df


# ---------------------------------------------------------------------------
# Load our derived stats
# ---------------------------------------------------------------------------

def load_our_stats() -> pd.DataFrame:
    df = pd.read_csv(INPUT_PATH)
    print(f"Loaded {len(df):,} pitchers from {INPUT_PATH}")
    df["_key"] = df["name"].apply(normalize_name)
    return df


# ---------------------------------------------------------------------------
# FIP from official component counts
# ---------------------------------------------------------------------------

def compute_official_fip(df_mlb: pd.DataFrame, df_ours: pd.DataFrame) -> pd.Series:
    """
    Compute FIP from MLB API component counts using the same cFIP constant
    we derived from Statcast.  Lets us check whether our FIP formula is right
    independent of whether our IP or ER counts are right.
    """
    # Derive cFIP from MLB league totals (same formula as calc_fip_statcast)
    lg = df_mlb[df_mlb["ip_official"] > 0]
    lg_hr  = lg["hr_official"].sum()
    lg_bb  = lg["bb_official"].sum()
    lg_hbp = lg["hbp_official"].sum()
    lg_k   = lg["k_official"].sum()
    lg_ip  = lg["ip_official"].sum()
    cfip   = LG_ERA - (13 * lg_hr + 3 * (lg_bb + lg_hbp) - 2 * lg_k) / lg_ip

    df_mlb = df_mlb.copy()
    df_mlb["fip_official"] = (
        (13 * df_mlb["hr_official"] + 3 * (df_mlb["bb_official"] + df_mlb["hbp_official"])
         - 2 * df_mlb["k_official"])
        / df_mlb["ip_official"].replace(0, float("nan"))
        + cfip
    ).round(2)
    return df_mlb


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    df_mlb  = fetch_mlb_stats()
    df_ours = load_our_stats()

    # Compute official FIP for validation
    df_mlb = compute_official_fip(df_mlb, df_ours)

    # ---- Join on normalized name ----
    merged = df_ours.merge(df_mlb, on="_key", how="inner")
    print(f"  Matched {len(merged):,} pitchers by name")

    # Filter: at least 10 IP in BOTH datasets
    qualified = merged[
        (merged["ip_official"] >= MIN_IP_DISPLAY) &
        (merged["IP"] >= MIN_IP_DISPLAY)
    ].copy()
    print(f"  Pitchers with >= {MIN_IP_DISPLAY} IP in both datasets: {len(qualified):,}")

    # ---- Differences ----
    qualified["ip_diff"]  = (qualified["IP"]  - qualified["ip_official"]).round(2)
    qualified["era_diff"] = (qualified["ERA"] - qualified["era_official"]).round(2)
    qualified["fip_diff"] = (qualified["FIP"] - qualified["fip_official"]).round(2)

    # ---- Top 20 by official IP ----
    top20 = qualified.sort_values("ip_official", ascending=False).head(20)

    display_cols = [
        "name",
        "IP", "ip_official", "ip_diff",
        "ERA", "era_official", "era_diff",
        "FIP", "fip_official", "fip_diff",
    ]

    col_headers = {
        "name": "Pitcher",
        "IP": "IP_ours", "ip_official": "IP_mlb", "ip_diff": "IP_diff",
        "ERA": "ERA_ours", "era_official": "ERA_mlb", "era_diff": "ERA_diff",
        "FIP": "FIP_ours", "fip_official": "FIP_mlb", "fip_diff": "FIP_diff",
    }

    display = top20[display_cols].rename(columns=col_headers)

    divider = "-" * 105
    print(f"\n{divider}")
    print("  TOP 20 PITCHERS BY OFFICIAL IP — DERIVED vs OFFICIAL COMPARISON")
    print(divider)
    print(display.to_string(index=False))

    # ---- Summary statistics ----
    print(f"\n{divider}")
    print("  SUMMARY STATISTICS  (all pitchers >= 10 IP in both datasets)")
    print(divider)

    stats = {}
    for label, col, off_col in [
        ("IP",  "IP",  "ip_official"),
        ("ERA", "ERA", "era_official"),
        ("FIP", "FIP", "fip_official"),
    ]:
        diff = qualified[col] - qualified[off_col]
        abs_diff = diff.abs()
        stats[label] = {
            "n":           len(diff),
            "mean_diff":   round(diff.mean(), 3),
            "mae":         round(abs_diff.mean(), 3),
            "max_err":     round(abs_diff.max(), 3),
            "pct_within_half": round((abs_diff <= 0.50).mean() * 100, 1),
            "pct_within_1":    round((abs_diff <= 1.00).mean() * 100, 1),
        }

    for label, s in stats.items():
        print(f"\n  {label}  (n={s['n']})")
        print(f"    Mean difference (ours - official) : {s['mean_diff']:+.3f}")
        print(f"    Mean absolute error               : {s['mae']:.3f}")
        print(f"    Max absolute error                : {s['max_err']:.3f}")
        print(f"    Within 0.50                       : {s['pct_within_half']:.1f}%")
        print(f"    Within 1.00                       : {s['pct_within_1']:.1f}%")

    # ---- Worst individual outliers ----
    print(f"\n{divider}")
    print("  LARGEST ERA DISCREPANCIES (ours vs official)")
    print(divider)
    worst_era = qualified.nlargest(10, "era_diff")[
        ["name", "IP", "ip_official", "ERA", "era_official", "era_diff", "FIP", "fip_official"]
    ].rename(columns=col_headers)
    print(worst_era.to_string(index=False))

    print(f"\n{divider}")
    print("  LARGEST IP DISCREPANCIES (ours vs official)")
    print(divider)
    worst_ip = qualified.reindex(qualified["ip_diff"].abs().nlargest(10).index)[
        ["name", "IP", "ip_official", "ip_diff", "ERA", "era_official"]
    ].rename(columns=col_headers)
    print(worst_ip.to_string(index=False))

    print()


if __name__ == "__main__":
    main()
