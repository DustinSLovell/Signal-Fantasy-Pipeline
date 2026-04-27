"""
build_cbs_fpts.py
=================
Scrapes CBS Fantasy Baseball season FPTS data (2022-2025) and runs
linear regression to derive category weights for the trade analyzer.

Hitter pages (by position, deduped): C, 1B, 2B, SS, 3B, OF, U
Pitcher pages (by role, deduped):    SP, RP

Outputs:
  data/cbs_hitter_fpts_{year}.csv
  data/cbs_pitcher_fpts_{year}.csv
  data/cbs_regression_results.txt  (human-readable report)

Usage:
    python build_cbs_fpts.py              # scrape all years + regress
    python build_cbs_fpts.py --scrape     # scrape only
    python build_cbs_fpts.py --regress    # regress only (uses cached CSVs)
    python build_cbs_fpts.py --year 2024  # single year scrape + regress
"""

import re
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import requests
from bs4 import BeautifulSoup

# ── config ────────────────────────────────────────────────────────────────────
BASE_DIR   = Path(__file__).parent
DATA_DIR   = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

# CBS Sports only retains 2024 and 2025 full-season stats publicly.
# Requesting 2022/2023 returns current-season (YTD) fallback data.
YEARS   = [2024, 2025]
DELAY   = 0.8   # seconds between requests (be polite)

HITTER_POSITIONS  = ["C", "1B", "2B", "SS", "3B", "OF", "U"]
PITCHER_POSITIONS = ["SP", "RP"]

CBS_URL  = "https://www.cbssports.com/fantasy/baseball/stats/{pos}/{year}/season/stats/"

HEADERS  = {
    "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    # NOTE: do NOT include Accept-Encoding here — requests adds its own gzip/deflate
    # header automatically. Adding 'br' (brotli) causes CBS to send brotli-compressed
    # responses that requests cannot decompress without the brotli package.
    "Referer":         "https://www.cbssports.com/",
}

# Short code → output column name
HITTER_COLS  = {"fpts": "fpts", "gp": "GP", "r": "R", "hr": "HR",
                "rbi": "RBI", "avg": "AVG", "sb": "SB"}
PITCHER_COLS = {"fpts": "fpts", "w": "W", "era": "ERA",
                "whip": "WHIP", "so": "K", "sv": "SV"}


# ── HTML helpers ──────────────────────────────────────────────────────────────

def _short_code(header_text: str) -> str:
    """'fptsFantasy Points' → 'fpts' | 'soStrikeouts' → 'so'"""
    m = re.match(r"^([a-z%/0-9]+)[A-Z]", header_text.strip())
    return m.group(1) if m else header_text.lower().split()[0]


def _clean(val: str):
    """'—' or '' → NaN; otherwise strip"""
    v = str(val).strip()
    return float("nan") if v in ("—", "", "nan") else v


def _player_name(cell) -> str:
    """Extract full player name from CellPlayerName--long span."""
    long_span = cell.find("span", class_="CellPlayerName--long")
    if long_span:
        link = long_span.find("a")
        if link:
            return link.get_text(strip=True)
    # Fallback: first anchor text
    link = cell.find("a")
    return link.get_text(strip=True) if link else cell.get_text(strip=True)


def _player_team(cell) -> str:
    long_span = cell.find("span", class_="CellPlayerName--long")
    if long_span:
        team_span = long_span.find("span", class_="CellPlayerName-team")
        if team_span:
            return team_span.get_text(strip=True)
    return ""


# ── page fetch ────────────────────────────────────────────────────────────────

def fetch_page(url: str, retries: int = 3) -> BeautifulSoup | None:
    for attempt in range(retries):
        try:
            r = requests.get(url, headers=HEADERS, timeout=20)
            if r.status_code == 200:
                return BeautifulSoup(r.text, "html.parser")
            print(f"    HTTP {r.status_code} for {url}")
            if r.status_code in (403, 429):
                wait = 30 * (attempt + 1)
                print(f"    Rate-limited — waiting {wait}s")
                time.sleep(wait)
        except Exception as e:
            print(f"    Request error ({e}), attempt {attempt+1}/{retries}")
            time.sleep(5 * (attempt + 1))
    return None


# ── table parser ──────────────────────────────────────────────────────────────

def parse_stats_table(soup: BeautifulSoup, col_map: dict) -> pd.DataFrame | None:
    """
    Parse the CBS stats table. col_map maps CBS short codes → our column names.
    Returns DataFrame with columns [name, team] + values from col_map.
    """
    table = soup.find("table")
    if not table:
        return None

    # Build column index from header
    thead = table.find("thead")
    if not thead:
        return None
    header_cells = thead.find_all(["th", "td"])
    headers = [cell.get_text(strip=True) for cell in header_cells]

    # Map header index → output name
    # Index 0 is always "Player"
    col_index = {}   # output_name → col_idx
    for idx, h in enumerate(headers):
        code = _short_code(h) if idx > 0 else "player"
        if code in col_map:
            col_index[col_map[code]] = idx

    if not col_index:
        print(f"    No matching columns found. Headers: {headers[:8]}")
        return None

    tbody = table.find("tbody")
    if not tbody:
        return None

    rows_out = []
    for tr in tbody.find_all("tr"):
        cells = tr.find_all("td")
        if not cells:
            continue

        name = _player_name(cells[0])
        team = _player_team(cells[0])
        row = {"name": name, "team": team}

        for col_name, idx in col_index.items():
            if idx < len(cells):
                row[col_name] = _clean(cells[idx].get_text(strip=True))
            else:
                row[col_name] = float("nan")

        rows_out.append(row)

    if not rows_out:
        return None

    df = pd.DataFrame(rows_out)
    # Cast numeric columns
    for col in col_map.values():
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


# ── scrape hitters ────────────────────────────────────────────────────────────

def scrape_hitters(year: int) -> pd.DataFrame:
    print(f"  Hitters {year}:")
    frames = []
    seen_names = set()

    for pos in HITTER_POSITIONS:
        url  = CBS_URL.format(pos=pos, year=year)
        soup = fetch_page(url)
        if soup is None:
            print(f"    {pos}: fetch failed, skipping")
            time.sleep(DELAY)
            continue

        df = parse_stats_table(soup, HITTER_COLS)
        if df is None or df.empty:
            print(f"    {pos}: no data")
            time.sleep(DELAY)
            continue

        # Deduplicate: keep only players not already seen
        new_mask   = ~df["name"].isin(seen_names)
        new_rows   = df[new_mask]
        seen_names.update(new_rows["name"].tolist())
        frames.append(new_rows)
        print(f"    {pos}: {len(df)} rows, {len(new_rows)} new (total unique: {len(seen_names)})")
        time.sleep(DELAY)

    if not frames:
        print(f"  No data collected for {year}")
        return pd.DataFrame()

    combined = pd.concat(frames, ignore_index=True)
    combined["year"] = year
    combined = combined.sort_values("fpts", ascending=False).reset_index(drop=True)
    return combined


# ── scrape pitchers ───────────────────────────────────────────────────────────

def scrape_pitchers(year: int) -> pd.DataFrame:
    print(f"  Pitchers {year}:")
    frames = []
    seen_names = set()

    for pos in PITCHER_POSITIONS:
        url  = CBS_URL.format(pos=pos, year=year)
        soup = fetch_page(url)
        if soup is None:
            print(f"    {pos}: fetch failed, skipping")
            time.sleep(DELAY)
            continue

        df = parse_stats_table(soup, PITCHER_COLS)
        if df is None or df.empty:
            print(f"    {pos}: no data")
            time.sleep(DELAY)
            continue

        new_mask   = ~df["name"].isin(seen_names)
        new_rows   = df[new_mask]
        seen_names.update(new_rows["name"].tolist())
        frames.append(new_rows)
        print(f"    {pos}: {len(df)} rows, {len(new_rows)} new (total unique: {len(seen_names)})")
        time.sleep(DELAY)

    if not frames:
        return pd.DataFrame()

    combined = pd.concat(frames, ignore_index=True)
    combined["year"] = year
    combined = combined.sort_values("fpts", ascending=False).reset_index(drop=True)
    return combined


# ── regression ────────────────────────────────────────────────────────────────

HITTER_FEATURES  = ["R", "HR", "RBI", "SB", "AVG"]
PITCHER_FEATURES = ["W", "ERA", "WHIP", "K", "SV"]


def _regress_one(df: pd.DataFrame, features: list[str], label: str,
                 use_ridge: bool = False) -> dict:
    """
    OLS (or Ridge) regression of fpts ~ features.
    Returns coef dict + R².

    use_ridge=True stabilizes coefficients when features are correlated
    (e.g. R/HR/RBI for hitters, ERA/WHIP for pitchers).
    """
    from sklearn.linear_model import LinearRegression, RidgeCV

    cols = ["fpts"] + features
    sub  = df[cols].dropna()
    if len(sub) < max(10, len(features) + 2):
        return {}

    X = sub[features].values
    y = sub["fpts"].values

    if use_ridge:
        model = RidgeCV(alphas=[0.1, 1.0, 10.0, 100.0, 1000.0], cv=5).fit(X, y)
    else:
        model = LinearRegression().fit(X, y)

    y_pred  = model.predict(X)
    ss_res  = ((y - y_pred) ** 2).sum()
    ss_tot  = ((y - y.mean()) ** 2).sum()
    r2      = 1 - ss_res / ss_tot if ss_tot > 0 else float("nan")

    result = {"n": len(sub), "r2": r2, "intercept": model.intercept_}
    for feat, coef in zip(features, model.coef_):
        result[feat] = coef
    if use_ridge:
        result["_alpha"] = getattr(model, "alpha_", None)
    return result


def run_regression(years_train: list[int] = (2024,),
                   year_oos: int = 2025) -> dict:
    """
    Run per-year and pooled regression for hitters and pitchers.
    Returns summary dict with all results.
    """
    from sklearn.linear_model import LinearRegression

    lines = []
    summary = {}

    divider = "=" * 72

    for ptype, features, col_suffix in [
        ("hitter",  HITTER_FEATURES,  "hitter"),
        ("pitcher", PITCHER_FEATURES, "pitcher"),
    ]:
        lines.append(divider)
        lines.append(f"  {ptype.upper()} REGRESSION  —  y = FPTS")
        lines.append(f"  Features: {features}")
        lines.append(divider)

        # Load all available years
        yearly_results = {}
        all_frames = []

        for year in years_train + [year_oos]:
            path = DATA_DIR / f"cbs_{col_suffix}_fpts_{year}.csv"
            if not path.exists():
                continue
            df = pd.read_csv(path)
            df["year"] = year
            all_frames.append(df)
            if year in years_train:
                res = _regress_one(df, features, ptype)
                if res:
                    yearly_results[year] = res

        if not yearly_results:
            lines.append("  No data available.")
            continue

        # Per-year table (all available years including OOS)
        all_yearly = {}
        for yr_check, df_check in [(yr, df) for yr, df in
                                    [(y, pd.read_csv(DATA_DIR / f"cbs_{col_suffix}_fpts_{y}.csv"))
                                     for y in [2024, 2025]
                                     if (DATA_DIR / f"cbs_{col_suffix}_fpts_{y}.csv").exists()]]:
            r = _regress_one(df_check, features, ptype)
            if r:
                all_yearly[yr_check] = r

        lines.append("")
        lines.append(f"  {'Year':<6} {'n':>5} {'R²':>6}  " +
                     "  ".join(f"{f:>8}" for f in features))
        lines.append("  " + "-" * 65)
        for year_y, res in sorted(all_yearly.items()):
            label = " (train)" if year_y in years_train else " (OOS)"
            feat_str = "  ".join(f"{res.get(f, float('nan')):>8.3f}" for f in features)
            lines.append(f"  {year_y:<6} {res['n']:>5} {res['r2']:>6.3f}  {feat_str}  {label}")

        # Stability: compare 2024 vs 2025 coefficients
        if len(all_yearly) >= 2:
            lines.append("")
            lines.append("  Stability (2024 vs 2025 coefficient comparison):")
            yr_keys = sorted(all_yearly.keys())
            for f in features:
                vals = [all_yearly[y].get(f, float("nan")) for y in yr_keys if not np.isnan(all_yearly[y].get(f, float("nan")))]
                if len(vals) >= 2:
                    delta  = abs(vals[1] - vals[0])
                    pct_ch = delta / abs(vals[0]) * 100 if vals[0] != 0 else float("nan")
                    flag   = "  ✓" if pct_ch < 15 else ("  ⚠" if pct_ch < 30 else "  ✗")
                    lines.append(f"    {f:<8}  {vals[0]:>+8.3f}  {vals[1]:>+8.3f}  Δ={pct_ch:.1f}%{flag}")

        # Pooled regression on train years — run both OLS and Ridge
        train_frames = [df for df in all_frames if df["year"].iloc[0] in years_train]
        if train_frames:
            pooled     = pd.concat(train_frames, ignore_index=True)
            pooled_ols = _regress_one(pooled, features, ptype, use_ridge=False)
            pooled_rdg = _regress_one(pooled, features, ptype, use_ridge=True)

            if pooled_ols:
                lines.append("")
                train_label = f"{min(years_train)}" if len(years_train) == 1 else f"{min(years_train)}-{max(years_train)}"
                lines.append(f"  Pooled ({train_label}) OLS:  n={pooled_ols['n']}  R²={pooled_ols['r2']:.4f}")
                for f in features:
                    lines.append(f"    {f:<8}  {pooled_ols.get(f, float('nan')):+.4f}")
                lines.append(f"    intercept  {pooled_ols['intercept']:+.4f}")

            if pooled_rdg:
                alpha = pooled_rdg.get("_alpha", "?")
                lines.append(f"  Pooled ({train_label}) Ridge (alpha={alpha}):  R²={pooled_rdg['r2']:.4f}")
                for f in features:
                    lines.append(f"    {f:<8}  {pooled_rdg.get(f, float('nan')):+.4f}")
                lines.append(f"    intercept  {pooled_rdg['intercept']:+.4f}")

            # Use Ridge for trade-analyzer config (more stable under collinearity)
            summary[ptype] = pooled_rdg if pooled_rdg else pooled_ols

            # OOS check — evaluate Ridge model on held-out year
            oos_frames = [df for df in all_frames if df["year"].iloc[0] == year_oos]
            if oos_frames and pooled_rdg:
                from sklearn.linear_model import RidgeCV
                oos_df  = oos_frames[0]
                oos_sub = oos_df[["fpts"] + features].dropna()
                if len(oos_sub) >= 10:
                    clean_p = pooled[["fpts"] + features].dropna()
                    ridge   = RidgeCV(alphas=[0.1, 1.0, 10.0, 100.0, 1000.0], cv=5)
                    ridge.fit(clean_p[features].values, clean_p["fpts"].values)
                    y_pred  = ridge.predict(oos_sub[features].values)
                    y_true  = oos_sub["fpts"].values
                    ss_r    = ((y_true - y_pred) ** 2).sum()
                    ss_t    = ((y_true - y_true.mean()) ** 2).sum()
                    oos_r2  = 1 - ss_r / ss_t
                    lines.append(f"  OOS {year_oos} (Ridge):  R²={oos_r2:.4f}  n={len(oos_sub)}"
                                 + ("  ✓" if oos_r2 >= 0.85 else "  ⚠"))

        lines.append("")

    # config.py output
    lines.append(divider)
    lines.append("  CONFIG.PY CONSTANTS  —  paste into config.py")
    lines.append(divider)
    lines.append("")

    if "hitter" in summary:
        res = summary["hitter"]
        lines.append("# CBS FPTS category weights — hitters (Ridge regression, train=2024, OOS=2025)")
        lines.append(f"# R² = {res['r2']:.4f}  (train) | n={res['n']}")
        lines.append("# Note: R/HR/RBI are collinear — Ridge stabilizes coefficients vs OLS.")
        lines.append(f"CBS_H_COEF_R         = {res.get('R', 0):+.4f}   # per run scored")
        lines.append(f"CBS_H_COEF_HR        = {res.get('HR', 0):+.4f}   # per home run")
        lines.append(f"CBS_H_COEF_RBI       = {res.get('RBI', 0):+.4f}   # per RBI")
        lines.append(f"CBS_H_COEF_SB        = {res.get('SB', 0):+.4f}   # per stolen base")
        lines.append(f"CBS_H_COEF_AVG       = {res.get('AVG', 0):+.4f}   # per .001 batting avg")
        lines.append(f"CBS_H_INTERCEPT      = {res['intercept']:+.4f}")
        lines.append(f"CBS_H_R2_TRAIN       = {res['r2']:.4f}")
        lines.append("")

    if "pitcher" in summary:
        res = summary["pitcher"]
        lines.append("# CBS FPTS category weights — pitchers (Ridge regression, train=2024, OOS=2025)")
        lines.append(f"# R² = {res['r2']:.4f}  (train) | n={res['n']}")
        lines.append("# Note: ERA/WHIP are collinear — Ridge stabilizes coefficients vs OLS.")
        lines.append(f"CBS_P_COEF_W         = {res.get('W', 0):+.4f}   # per win")
        lines.append(f"CBS_P_COEF_ERA       = {res.get('ERA', 0):+.4f}   # per ERA point (expect negative)")
        lines.append(f"CBS_P_COEF_WHIP      = {res.get('WHIP', 0):+.4f}   # per WHIP point (expect negative)")
        lines.append(f"CBS_P_COEF_K         = {res.get('K', 0):+.4f}   # per strikeout")
        lines.append(f"CBS_P_COEF_SV        = {res.get('SV', 0):+.4f}   # per save")
        lines.append(f"CBS_P_INTERCEPT      = {res['intercept']:+.4f}")
        lines.append(f"CBS_P_R2_TRAIN       = {res['r2']:.4f}")
        lines.append("")

    report = "\n".join(lines)

    out_path = DATA_DIR / "cbs_regression_results.txt"
    out_path.write_text(report, encoding="utf-8")
    print(f"\nRegression report → {out_path}")
    print(report)
    return summary


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    args = sys.argv[1:]
    do_scrape  = "--scrape"  in args or "--regress" not in args
    do_regress = "--regress" in args or "--scrape"  not in args

    # Single-year override
    target_years = YEARS
    if "--year" in args:
        idx = args.index("--year")
        if idx + 1 < len(args):
            target_years = [int(args[idx + 1])]

    # Scrape
    if do_scrape:
        print("=" * 65)
        print("  CBS Fantasy Baseball FPTS Scraper")
        print(f"  Years: {target_years}")
        print("=" * 65)

        for year in target_years:
            print(f"\n── Year {year} ──────────────────────────────────────────────")

            hitter_path  = DATA_DIR / f"cbs_hitter_fpts_{year}.csv"
            pitcher_path = DATA_DIR / f"cbs_pitcher_fpts_{year}.csv"

            if hitter_path.exists() and "--force" not in args:
                print(f"  Hitter {year}: cached ({hitter_path.name})")
            else:
                h_df = scrape_hitters(year)
                if not h_df.empty:
                    h_df.to_csv(hitter_path, index=False)
                    print(f"  Saved {len(h_df)} hitters → {hitter_path.name}")
                time.sleep(DELAY * 2)

            if pitcher_path.exists() and "--force" not in args:
                print(f"  Pitcher {year}: cached ({pitcher_path.name})")
            else:
                p_df = scrape_pitchers(year)
                if not p_df.empty:
                    p_df.to_csv(pitcher_path, index=False)
                    print(f"  Saved {len(p_df)} pitchers → {pitcher_path.name}")
                time.sleep(DELAY * 2)

    # Regression
    if do_regress:
        train_years = [y for y in [2024] if (DATA_DIR / f"cbs_hitter_fpts_{y}.csv").exists()]
        oos_year    = 2025

        if not train_years:
            print("\nNo training data found. Run --scrape first.")
            return

        print(f"\nRunning regression on {train_years}, OOS={oos_year}")
        run_regression(train_years, oos_year)


if __name__ == "__main__":
    main()
