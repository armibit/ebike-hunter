#!/usr/bin/env python3
"""Generate static HTML dashboard from DB listings."""

import json
import re
import sys
from pathlib import Path
from datetime import datetime

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from db.database import Database
import yaml


def _attr(value) -> str:
    """Escape a value for safe embedding inside a double-quoted HTML attribute."""
    if value is None:
        return ""
    return (
        str(value)
        .replace("&", "&amp;")
        .replace('"', "&quot;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _format_price(bike: dict, previous_price: str = None) -> str:
    """Show the price in the currency the listing was actually posted in,
    without conversions. Scoring/filtering still use price_chf internally."""
    price_raw = bike.get("price_raw")
    currency = (bike.get("currency") or "").upper()
    price_chf = bike.get("price_chf")
    if price_raw is None:
        text = f"{price_chf:.0f} CHF" if price_chf is not None else "N/A"
    else:
        text = f"{price_raw:.0f} {currency}".strip()
    if previous_price:
        text += f"<br><small style='color: var(--text-muted);'>era: {previous_price}</small>"
    return text


def _get_previous_price(history: list) -> str:
    """Get previous price from history. If 2+ snapshots, return the second-to-last."""
    if len(history) < 2:
        return None
    prev = history[-2]
    price_raw = prev.get("price_raw")
    currency = (prev.get("currency") or "").upper()
    if price_raw is None:
        return None
    return f"{price_raw:.0f} {currency}".strip()


def _format_date(iso_str) -> str:
    if not iso_str:
        return "N/A"
    try:
        return datetime.fromisoformat(str(iso_str)).strftime("%d/%m/%Y")
    except ValueError:
        return str(iso_str)[:10]


def _combine_analysis(bike: dict) -> str:
    """Short plain-text summary for the compact Top-10 cards — heuristic
    verdict plus the AI one if present. The full per-listing modal uses the
    structured HTML in _build_detail_html() instead; this stays plain text
    since it's just squeezed into a small card, not a detail view."""
    parts = []
    if bike.get("user_analysis"):
        parts.append(bike["user_analysis"])
    if bike.get("ai_analysis"):
        ai_score = bike.get("ai_score")
        score_note = f" (score: {ai_score:.0f}/100)" if ai_score is not None else ""
        parts.append(f"🤖 Verdetto AI{score_note}:\n{bike['ai_analysis']}")
    return "\n\n".join(parts)


def _render_text_block(text) -> str:
    """Turn the light markdown our own generate_user_analysis() (and the AI
    verdict prompt) use — **bold**, "• " bullet lines, blank-line-separated
    paragraphs — into real HTML. Escapes first, so this only recognizes
    those two specific patterns; it is not a general markdown parser."""
    if not text:
        return ""
    parts = []
    for para in str(text).split("\n\n"):
        lines = [line.strip() for line in para.split("\n") if line.strip()]
        if not lines:
            continue
        if all(line.startswith("•") for line in lines):
            items = "".join(f"<li>{_bold(_attr(line.lstrip('•').strip()))}</li>" for line in lines)
            parts.append(f"<ul>{items}</ul>")
        else:
            parts.append("<p>" + "<br>".join(_bold(_attr(line)) for line in lines) + "</p>")
    return "".join(parts)


def _bold(escaped_text: str) -> str:
    """Convert **markers** to <strong> in text _attr() already escaped —
    asterisks aren't HTML-special so they survive escaping untouched, and
    this must run after it so ** in the seller's own text isn't matched."""
    return re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped_text)


def _build_price_history_html(history: list) -> str:
    if len(history) < 2:
        return ""
    chips = '<span class="price-arrow">→</span>'.join(
        f'<span class="price-chip">{snap["price_raw"]:.0f} {_attr(snap["currency"])}<small>{_format_date(snap["captured_at"])}</small></span>'
        for snap in history
    )
    return f'<div class="detail-section"><h3>💰 Storico prezzo</h3><div class="price-history">{chips}</div></div>'


_SUSPENSION_LABELS = {"full_suspension": "Full suspension", "hardtail": "Hardtail", "unknown": "Non specificata"}
_BRAKES_LABELS = {"four_piston": "4 pistoncini (top)", "two_piston": "2 pistoncini", "unknown": "Non specificati"}


def _score_class(value) -> str:
    value = value or 0
    return "high" if value >= 80 else "mid" if value >= 65 else "low"


def _build_spec_table_html(bike: dict) -> str:
    """Compact 2-column grid of only the specs actually known — specs are
    the first thing to scan in the detail card, so an "N/A"/"Non
    specificato" row for every field the parser didn't catch just pads the
    card with negative space dressed up as content. Frame size is the one
    exception: "not found" there is itself a decision-relevant fact (the
    buyer profile targets specific sizes), so it's always shown."""
    items = []

    motor_bits = [b for b in (bike.get("motor_brand"), bike.get("motor_model")) if b]
    if motor_bits:
        motor_text = _attr(" ".join(motor_bits))
        if bike.get("motor_torque_nm"):
            motor_text += f" · {bike['motor_torque_nm']:.0f} Nm"
        motor_text += (
            ' <span class="badge badge-warn">⚠️ da verificare</span>'
            if bike.get("motor_verified") == 0
            else ' <span class="badge badge-ok">✓ verificato</span>'
        )
        items.append(("Motore", motor_text))

    if bike.get("battery_capacity_wh"):
        items.append(("Batteria", f"{bike['battery_capacity_wh']:.0f} Wh"))

    items.append(("Taglia", _attr(bike.get("frame_size")) or "N/A"))

    if bike.get("model_year"):
        items.append(("Anno modello", bike["model_year"]))

    if bike.get("odometer_km"):
        items.append(("Percorrenza", f"{bike['odometer_km']:.0f} km"))

    if bike.get("suspension_type") and bike["suspension_type"] != "unknown":
        suspension_text = _SUSPENSION_LABELS.get(bike["suspension_type"], _attr(bike["suspension_type"]))
        if bike.get("travel_front_mm"):
            suspension_text += f" · {bike['travel_front_mm']:.0f}mm"
        items.append(("Sospensione", suspension_text))

    if bike.get("brakes_tier") and bike["brakes_tier"] != "unknown":
        items.append(("Freni", _BRAKES_LABELS.get(bike["brakes_tier"], _attr(bike["brakes_tier"]))))

    items_html = "".join(
        f'<div class="spec-item"><div class="spec-label">{label}</div><div class="spec-value">{value}</div></div>'
        for label, value in items
    )
    return f'<div class="detail-section"><h3>⚙️ Specifiche</h3><div class="spec-grid">{items_html}</div></div>'


def _build_score_breakdown_html(bike: dict) -> str:
    parts = [
        ("Prezzo", bike.get("score_price_value")),
        ("Componenti", bike.get("score_component_quality")),
        ("Condizione / Km", bike.get("score_condition_mileage")),
        ("Posizione", bike.get("score_location_proximity")),
        ("Taglia / Escursione", bike.get("score_fit_geometry")),
    ]
    rows_html = "".join(
        f'<div class="score-row"><span class="score-row-label">{label}</span>'
        f'<div class="score-track"><div class="score-fill" style="width:{(value or 0):.0f}%"></div></div>'
        f'<span class="score-row-value">{(value or 0):.0f}</span></div>'
        for label, value in parts
    )
    total = bike.get("score_total") or 0
    # Collapsed by default (native <details>, no JS needed) — the total is
    # already in the top bar; this per-component breakdown is reference
    # detail you open on purpose, not something that should cost scroll
    # space on every listing you open.
    return (
        '<details class="detail-section score-accordion">'
        f'<summary>📊 Dettaglio punteggio euristico ({total:.0f}/100)</summary>'
        f'<div class="score-breakdown-body">{rows_html}</div>'
        '</details>'
    )


def _build_red_flags_html(bike: dict) -> str:
    if not bike.get("has_red_flag"):
        return ""
    raw = bike.get("red_flag_details")
    try:
        flags = json.loads(raw) if raw else []
    except (TypeError, ValueError):
        flags = []
    if not flags:
        return ""
    items = "".join(f"<li>{_attr(flag)}</li>" for flag in flags)
    return f'<div class="detail-section detail-warning"><h3>⚠️ Segnalazioni</h3><ul>{items}</ul></div>'


def _build_detail_html(bike: dict, history: list) -> str:
    """Structured detail card for the per-listing modal — replaces the old
    single wall-of-escaped-text approach (which also had a real bug: it
    escaped newlines to the literal two characters "\\n" for a JS-string
    context that was never actually used, so they rendered as literal
    backslash-n in the page instead of line breaks).

    Ordered by what's actually useful to scan first, top to bottom: a
    compact price+score+link strip, then specs (the primary "does this
    match?" check), then any warnings, then the two written verdicts
    (heuristic, then AI), and only at the bottom the price history and the
    score sub-breakdown — reference detail you dig into, not headline info,
    so it shouldn't push the important stuff below the fold."""
    total = bike.get("score_total") or 0
    top_bar = (
        '<div class="detail-section">'
        '<div class="detail-topbar">'
        f'<span class="detail-price">{_attr(_format_price(bike))}</span>'
        f'<span class="score {_score_class(total)}">{total:.0f}</span>'
        f'<a href="{_attr(bike.get("url"))}" target="_blank">Apri annuncio originale ↗</a>'
        "</div>"
        f'<p class="detail-sub">Visto la prima volta il {_format_date(bike.get("first_seen_at"))}</p>'
        "</div>"
    )

    sections = [
        top_bar,
        _build_spec_table_html(bike),
        _build_red_flags_html(bike),
    ]

    if bike.get("user_analysis"):
        sections.append(
            '<div class="detail-section"><h3>📝 Valutazione automatica</h3>'
            f'{_render_text_block(bike["user_analysis"])}</div>'
        )

    if bike.get("ai_analysis"):
        ai_score = bike.get("ai_score")
        score_note = f"{ai_score:.0f}/100" if ai_score is not None else "N/A"
        sections.append(
            '<div class="detail-section detail-ai"><h3>🤖 Verdetto AI '
            f'<span class="badge badge-ai">{score_note}</span></h3>'
            f'{_render_text_block(bike["ai_analysis"])}</div>'
        )

    sections.append(_build_price_history_html(history))
    sections.append(_build_score_breakdown_html(bike))

    return "".join(s for s in sections if s)


def render_dashboard_html(db_path: str, interactive: bool = False) -> str:
    """Build the dashboard HTML from the DB.

    interactive=True renders the reject/mark-sold/restore buttons and the
    spec-correction form, wired to POST /api/listings/<id>/... — only
    meaningful when served by server.py, since a static file:// page has
    nothing to send those requests to. generate_dashboard() below always
    calls this with interactive=False so the auto-regenerated index.html
    (written by run.py/analyze.py) stays a plain read-only snapshot.

    Every status is always fetched — REJECTED/SOLD/DELISTED listings stay
    visible (greyed out, see the "sold"/"rejected" row classes) rather than
    disappearing from the page, and the client-side "Stato" filter picks
    among them, same as every other filter here. Nothing to toggle
    server-side, so there's no separate "show all" URL/mode to keep in sync.
    """
    db = Database(db_path)

    cursor = db.conn.cursor()
    cursor.execute("""
    SELECT
        l.rowid AS numeric_id,
        l.id, l.portal, l.title, l.price_raw, l.currency, l.price_chf, l.distance_km, l.url,
        l.first_seen_at, l.last_seen_at, l.status, l.is_favorite,
        l.user_analysis, l.ai_analysis, l.ai_score,
        s.motor_brand, s.motor_model, s.motor_torque_nm, s.motor_verified,
        s.battery_capacity_wh, s.frame_size, s.model_year, s.odometer_km,
        s.travel_front_mm, s.brakes_tier, s.suspension_type,
        s.has_red_flag, s.red_flag_details,
        sc.score_total, sc.score_price_value, sc.score_component_quality,
        sc.score_condition_mileage, sc.score_location_proximity, sc.score_fit_geometry,
        CASE WHEN l.ai_score IS NOT NULL THEN 0.6 * sc.score_total + 0.4 * l.ai_score
             ELSE sc.score_total END AS ranking_score
    FROM listings l
    LEFT JOIN specifications s ON l.id = s.listing_id
    LEFT JOIN scores sc ON l.id = sc.listing_id
    ORDER BY l.is_favorite DESC,
             CASE WHEN l.status IN ('SOLD', 'REJECTED', 'DELISTED') THEN 1 ELSE 0 END,
             COALESCE(ranking_score, 0) DESC, l.price_chf ASC
    """)

    listings = [dict(row) for row in cursor.fetchall()]

    # Price history (listing_snapshots), grouped by listing — one query for
    # all listings rather than one per row, then sliced per-listing below.
    cursor.execute("""
    SELECT listing_id, price_raw, currency, captured_at
    FROM listing_snapshots
    ORDER BY listing_id, captured_at ASC
    """)
    history_by_id = {}
    for row in cursor.fetchall():
        history_by_id.setdefault(row["listing_id"], []).append(dict(row))

    db.close()

    # Top 10
    top_10 = listings[:10]
    ai_analyzed_count = sum(1 for bike in listings if bike.get("ai_analysis"))

    # Generate HTML
    html = f"""<!DOCTYPE html>
<html lang="it">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>E-Bike Hunter Dashboard</title>
    <style>
        :root {{
            --bg: #f6f7f9;
            --surface: #ffffff;
            --border: #e5e7eb;
            --text: #1f2937;
            --text-muted: #6b7280;
            --primary: #2563eb;
            --primary-dark: #1d4ed8;
            --primary-light: #eff6ff;
            --success: #16a34a;
            --success-bg: #dcfce7;
            --warning: #d97706;
            --warning-bg: #fef3c7;
            --danger: #dc2626;
            --danger-bg: #fee2e2;
            --radius: 10px;
            --radius-sm: 7px;
        }}
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: var(--bg); color: var(--text); -webkit-font-smoothing: antialiased; }}
        .container {{ max-width: 1440px; margin: 0 auto; padding: 32px 24px 60px; }}
        a {{ color: var(--primary); text-decoration: none; }}
        a:hover {{ text-decoration: underline; }}

        h1 {{ font-size: 26px; font-weight: 700; letter-spacing: -0.02em; margin-bottom: 6px; }}
        .meta {{ color: var(--text-muted); font-size: 13px; margin-bottom: 4px; }}
        .meta a {{ font-weight: 600; }}
        .readonly-banner {{ background: var(--warning-bg); color: #92400e; padding: 12px 16px; border-radius: var(--radius-sm); margin: 14px 0; font-size: 13px; line-height: 1.5; }}
        .readonly-banner code {{ background: rgba(0,0,0,0.08); padding: 1px 6px; border-radius: 4px; font-size: 12px; }}

        .section-title {{ font-size: 15px; font-weight: 700; margin: 36px 0 14px; color: var(--text); }}

        .filters {{ background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); margin: 18px 0 10px; box-shadow: 0 1px 2px rgba(0,0,0,.04); overflow: hidden; }}
        .filters-header {{ display: flex; align-items: center; justify-content: space-between; padding: 13px 20px; border-bottom: 1px solid var(--border); background: #fafbfc; }}
        .filters-title {{ font-size: 12px; font-weight: 700; color: var(--text); text-transform: uppercase; letter-spacing: .04em; }}
        .filters-body {{ padding: 18px 20px; display: grid; grid-template-columns: repeat(auto-fill, minmax(130px, 1fr)); gap: 16px 20px; align-items: end; }}
        .filter-group {{ display: flex; flex-direction: column; gap: 6px; min-width: 0; }}
        .filter-group label {{ font-size: 11px; font-weight: 700; color: var(--text-muted); text-transform: uppercase; letter-spacing: .04em; }}
        .filter-group input, .filter-group select {{ width: 100%; height: 33px; padding: 0 10px; border: 1px solid var(--border); border-radius: var(--radius-sm); font-size: 13px; background: var(--surface); color: var(--text); }}
        .filter-group input:focus, .filter-group select:focus {{ outline: none; border-color: var(--primary); box-shadow: 0 0 0 3px var(--primary-light); }}
        .range-row {{ display: flex; align-items: center; gap: 8px; height: 33px; }}
        .range-row input[type="range"] {{ flex: 1; min-width: 0; width: auto; height: auto; padding: 0; border: none; }}
        .range-value {{ font-size: 12px; font-weight: 700; color: var(--primary); min-width: 32px; text-align: right; flex-shrink: 0; }}
        .filter-checkbox {{ flex-direction: row; align-items: center; gap: 6px; font-weight: 500; text-transform: none; letter-spacing: normal; color: var(--text); font-size: 13px; height: 33px; }}
        .filter-checkbox input {{ width: auto; height: auto; flex-shrink: 0; }}
        .btn-reset {{ padding: 6px 14px; background: var(--surface); color: var(--danger); border: 1px solid var(--danger-bg); border-radius: var(--radius-sm); cursor: pointer; font-size: 12px; font-weight: 600; flex-shrink: 0; }}
        .btn-reset:hover {{ background: var(--danger-bg); }}

        .top-10 {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 12px; }}
        .top-item {{ background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); padding: 14px 16px; box-shadow: 0 1px 2px rgba(0,0,0,.03); }}
        .top-rank {{ display: inline-flex; align-items: center; justify-content: center; width: 20px; height: 20px; border-radius: 50%; background: var(--primary-light); color: var(--primary); font-size: 11px; font-weight: 700; margin-right: 6px; }}
        .top-item a {{ font-weight: 600; color: var(--text); }}
        .top-portal {{ color: var(--text-muted); font-size: 12px; }}
        .top-analysis {{ font-size: 12px; color: var(--text-muted); margin: 8px 0; line-height: 1.5; max-height: 4.5em; overflow: hidden; }}
        .top-meta {{ font-size: 12px; color: var(--text); font-weight: 600; padding-top: 8px; border-top: 1px solid var(--border); }}

        table {{ width: 100%; border-collapse: collapse; background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); overflow: visible; box-shadow: 0 1px 2px rgba(0,0,0,.04); }}
        thead {{ position: sticky; top: 0; z-index: 20; }}
        thead th {{ background: #fafbfc; color: var(--text-muted); text-transform: uppercase; font-size: 11px; letter-spacing: .04em; font-weight: 700; padding: 12px 14px; text-align: left; border-bottom: 1px solid var(--border); white-space: nowrap; }}
        thead th:not(.no-sort) {{ cursor: pointer; user-select: none; }}
        thead th:not(.no-sort):hover {{ color: var(--primary); }}
        thead th.sorted-asc::after {{ content: " ▲"; color: var(--primary); }}
        thead th.sorted-desc::after {{ content: " ▼"; color: var(--primary); }}
        tbody td {{ padding: 12px 14px; border-bottom: 1px solid var(--border); font-size: 13px; vertical-align: middle; }}
        tbody tr:last-child td {{ border-bottom: none; }}
        tbody tr:hover {{ background: #fafbfc; }}
        tbody tr.sold {{ opacity: .45; }}

        .title-link {{ font-weight: 600; color: var(--text); }}
        .title-meta {{ color: var(--text-muted); font-size: 12px; margin-top: 3px; }}
        .ai-icon {{ font-size: 11px; cursor: default; }}
        .new-icon {{ font-size: 11px; cursor: default; }}
        .numeric-id {{ color: var(--text-muted); font-size: 12px; font-variant-numeric: tabular-nums; }}

        .score {{ display: inline-flex; align-items: center; justify-content: center; min-width: 42px; padding: 5px 10px; border-radius: 999px; font-weight: 700; font-size: 13px; }}
        .score.high {{ background: var(--success-bg); color: var(--success); }}
        .score.mid {{ background: var(--warning-bg); color: var(--warning); }}
        .score.low {{ background: var(--danger-bg); color: var(--danger); }}

        .status {{ display: inline-block; padding: 4px 10px; border-radius: 999px; font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: .02em; background: var(--success-bg); color: var(--success); }}
        .status.new {{ background: #dbeafe; color: #1e40af; }}
        .status.price-drop {{ background: #fce7f3; color: #9d174d; }}
        .status.sold {{ background: #f3f4f6; color: #6b7280; text-decoration: line-through; }}
        .status.rejected {{ background: var(--danger-bg); color: var(--danger); }}

        .motor {{ background: #f3f4f6; color: var(--text); padding: 4px 9px; border-radius: 6px; font-size: 12px; font-weight: 500; display: inline-block; }}

        .row-actions {{ display: flex; align-items: center; gap: 6px; }}
        /* Each row action has its own colour at rest, not only on hover —
           four identical pale-grey squares read as one blob until you
           hover each in turn to find out what it does. */
        .icon-btn {{ width: 30px; height: 30px; display: inline-flex; align-items: center; justify-content: center; border-radius: var(--radius-sm); border: 1px solid var(--border); background: var(--surface); color: var(--text-muted); cursor: pointer; font-size: 13px; line-height: 1; transition: filter .15s; }}
        .icon-btn:hover {{ filter: brightness(0.96); }}
        .icon-star {{ border: none; background: none; font-size: 18px; color: #f59e0b; }}
        .icon-star:hover {{ filter: none; }}
        .icon-details {{ background: var(--primary-light); border-color: #bfdbfe; color: var(--primary); }}
        .icon-danger {{ background: var(--danger-bg); border-color: #fecaca; color: var(--danger); }}
        .icon-success {{ background: var(--success-bg); border-color: #bbf7d0; color: var(--success); }}
        .icon-delete {{ background: #f5e6e8; border-color: #f5c6cc; color: #c41e3a; }}
        .btn-details {{ padding: 6px 12px; background: var(--primary); color: white; border: none; border-radius: var(--radius-sm); cursor: pointer; font-size: 12px; font-weight: 600; white-space: nowrap; }}
        .btn-details:hover {{ background: var(--primary-dark); }}

        .modal {{ display: none; position: fixed; z-index: 1000; left: 0; top: 0; width: 100%; height: 100%; background-color: rgba(15,23,42,0.5); }}
        .modal.show {{ display: block; }}
        .modal-content {{ background-color: var(--surface); margin: 4% auto; padding: 24px; border-radius: var(--radius); width: 88%; max-width: 900px; max-height: 84vh; overflow-y: auto; box-shadow: 0 20px 40px rgba(0,0,0,0.2); }}
        .modal-header-actions {{ display: flex; justify-content: flex-end; align-items: center; gap: 8px; margin-bottom: 4px; }}
        .modal-nav-btn {{ width: 30px; height: 30px; border-radius: var(--radius-sm); border: 1px solid var(--border); background: var(--surface); color: var(--text); cursor: pointer; font-size: 15px; }}
        .modal-nav-btn:hover {{ background: var(--bg); }}
        .modal-nav-btn:disabled {{ opacity: .3; cursor: default; }}
        .modal-nav-btn:disabled:hover {{ background: var(--surface); }}
        .modal-close {{ font-size: 24px; font-weight: bold; cursor: pointer; color: var(--text-muted); line-height: 1; margin-left: 4px; }}
        .modal-close:hover {{ color: var(--text); }}
        .modal h2 {{ margin: 0 0 18px; font-size: 18px; }}
        .modal-body {{ font-size: 14px; line-height: 1.6; }}

        .detail-section {{ margin-bottom: 18px; padding-bottom: 18px; border-bottom: 1px solid var(--border); }}
        .detail-section:last-child {{ border-bottom: none; margin-bottom: 0; padding-bottom: 0; }}
        .detail-section h3 {{ font-size: 13px; margin-bottom: 10px; color: var(--primary); text-transform: uppercase; letter-spacing: .03em; }}
        .detail-section p {{ margin: 6px 0; }}
        .detail-section ul {{ margin: 6px 0 6px 20px; }}
        .detail-topbar {{ display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }}
        .detail-price {{ font-size: 20px; font-weight: 700; }}
        .detail-sub {{ font-size: 12px; color: var(--text-muted); margin-top: 4px; }}
        .detail-warning {{ background: var(--warning-bg); border-radius: var(--radius-sm); padding: 14px 16px; border-bottom: none; }}
        .detail-warning h3 {{ color: #92400e; }}
        .detail-ai {{ background: var(--primary-light); border-radius: var(--radius-sm); padding: 14px 16px; border-bottom: none; }}

        .spec-grid {{ display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px 20px; }}
        .spec-item {{ min-width: 0; }}
        .spec-label {{ font-size: 11px; color: var(--text-muted); text-transform: uppercase; letter-spacing: .03em; margin-bottom: 2px; }}
        .spec-value {{ font-size: 14px; font-weight: 600; }}

        .price-history {{ display: flex; flex-wrap: wrap; align-items: center; gap: 6px; }}
        .price-chip {{ background: var(--bg); border-radius: var(--radius-sm); padding: 6px 10px; font-size: 13px; font-weight: 600; display: flex; flex-direction: column; align-items: center; }}
        .price-chip small {{ font-weight: normal; color: var(--text-muted); font-size: 11px; }}
        .price-arrow {{ color: var(--text-muted); }}

        .badge {{ display: inline-block; padding: 2px 8px; border-radius: 999px; font-size: 11px; font-weight: 600; margin-left: 4px; }}
        .badge-ok {{ background: var(--success-bg); color: var(--success); }}
        .badge-warn {{ background: var(--warning-bg); color: var(--warning); }}
        .badge-ai {{ background: #ede9fe; color: #6d28d9; }}

        .score-accordion summary {{ font-size: 13px; color: var(--primary); text-transform: uppercase; letter-spacing: .03em; cursor: pointer; list-style: none; }}
        .score-accordion summary::-webkit-details-marker {{ display: none; }}
        .score-accordion summary::before {{ content: "▸ "; display: inline-block; }}
        .score-accordion[open] summary::before {{ content: "▾ "; }}
        .score-breakdown-body {{ margin-top: 12px; }}
        .score-row {{ display: flex; align-items: center; gap: 10px; margin: 7px 0; font-size: 12px; }}
        .score-row-label {{ width: 140px; color: var(--text-muted); flex-shrink: 0; }}
        .score-track {{ flex: 1; background: var(--bg); border-radius: 4px; height: 8px; overflow: hidden; }}
        .score-fill {{ background: var(--primary); height: 100%; }}
        .score-row-value {{ width: 28px; text-align: right; font-weight: 600; flex-shrink: 0; }}

        .btn-reject {{ padding: 8px 14px; background: var(--danger); color: white; border: none; border-radius: var(--radius-sm); cursor: pointer; font-size: 12px; font-weight: 600; }}
        .btn-sold {{ padding: 8px 14px; background: #6b7280; color: white; border: none; border-radius: var(--radius-sm); cursor: pointer; font-size: 12px; font-weight: 600; }}
        .btn-restore {{ padding: 8px 14px; background: var(--primary); color: white; border: none; border-radius: var(--radius-sm); cursor: pointer; font-size: 12px; font-weight: 600; }}
        .btn-save {{ padding: 8px 14px; background: var(--success); color: white; border: none; border-radius: var(--radius-sm); cursor: pointer; font-size: 12px; font-weight: 600; }}
        .modal-actions {{ margin-top: 15px; padding-top: 15px; border-top: 1px solid var(--border); display: flex; gap: 8px; }}
        .edit-specs {{ margin-top: 15px; padding-top: 15px; border-top: 1px solid var(--border); }}
        .edit-specs h3 {{ font-size: 13px; margin-bottom: 10px; text-transform: uppercase; letter-spacing: .03em; color: var(--primary); }}
        .edit-specs .edit-fields {{ display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 12px; }}
        .edit-specs label {{ display: flex; flex-direction: column; gap: 4px; font-size: 11px; font-weight: 700; color: var(--text-muted); text-transform: uppercase; letter-spacing: .03em; }}
        .edit-specs input, .edit-specs select {{ padding: 7px 9px; border: 1px solid var(--border); border-radius: var(--radius-sm); font-size: 13px; }}

        .editable-cell {{ cursor: pointer; }}
        .editable-cell:hover {{ background: var(--bg); outline: 1px dashed var(--border); }}
        .cell-edit {{ display: flex; align-items: center; gap: 4px; flex-wrap: wrap; }}
        .cell-edit-input {{ padding: 4px 6px; border: 1px solid var(--primary); border-radius: 4px; font-size: 12px; width: 90px; }}
        .cell-edit-actions {{ display: inline-flex; gap: 3px; }}
        .cell-edit-btn {{ width: 22px; height: 22px; display: inline-flex; align-items: center; justify-content: center; border: none; border-radius: 4px; cursor: pointer; font-size: 11px; line-height: 1; }}
        .cell-edit-save {{ background: var(--success); color: white; }}
        .cell-edit-cancel {{ background: var(--danger); color: white; }}

        .back-to-top {{ display: none; position: fixed; bottom: 24px; right: 24px; z-index: 500; width: 44px; height: 44px; border: none; border-radius: 50%; background: var(--primary); color: white; font-size: 18px; cursor: pointer; box-shadow: 0 2px 8px rgba(0,0,0,0.25); }}
        .back-to-top.visible {{ display: block; }}
        .back-to-top:hover {{ opacity: 0.85; }}
    </style>
</head>
<body>
    <button id="backToTop" class="back-to-top" title="Torna in cima">↑</button>
    <div class="container">
        <h1>🚲 E-Bike Hunter Dashboard</h1>
        <div class="meta">Aggiornato: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | {len(listings)} annunci trovati | 🤖 {ai_analyzed_count} con analisi AI</div>
        <div class="meta">⚠️ Portali bloccati (controllo manuale): <a href="https://www.decathlon.ch/search?from=0&size=40" target="_blank">Decathlon.ch</a> (Cloudflare)</div>
        {'<div class="readonly-banner">📄 Questa è una copia statica, sola lettura (generata da <code>run.py</code>/<code>analyze.py</code>/<code>generate_dashboard.py</code>). Per scartare, segnare venduta/preferita o correggere le specifiche a mano, avvia <code>python3 server.py</code> invece di aprire questo file.</div>' if not interactive else ''}

        <div class="filters">
            <div class="filters-header">
                <div class="filters-title">🔍 Filtri di ricerca</div>
                <button class="btn-reset" onclick="resetFilters()">↺ Reset</button>
            </div>
            <div class="filters-body">
                <div class="filter-group">
                    <label>Budget min (CHF)</label>
                    <div class="range-row">
                        <input type="range" id="priceMin" min="0" max="3000" step="100" value="0">
                        <span class="range-value" id="priceMinVal">0</span>
                    </div>
                </div>
                <div class="filter-group">
                    <label>Budget max (CHF)</label>
                    <div class="range-row">
                        <input type="range" id="priceMax" min="1500" max="3500" step="100" value="3000">
                        <span class="range-value" id="priceMaxVal">3000</span>
                    </div>
                </div>
                <div class="filter-group">
                    <label>Distanza km</label>
                    <input type="number" id="distMax" value="100" min="0" max="1000">
                </div>
                <div class="filter-group">
                    <label>Motore</label>
                    <select id="motorFilter">
                        <option value="">Tutti</option>
                        <option value="Bosch">Bosch</option>
                        <option value="Shimano">Shimano</option>
                        <option value="Yamaha">Yamaha</option>
                        <option value="Brose">Brose</option>
                    </select>
                </div>
                <div class="filter-group">
                    <label>Batteria min (Wh)</label>
                    <input type="number" id="batteryMin" value="400" min="0" max="1000">
                </div>
                <div class="filter-group">
                    <label>Taglia</label>
                    <select id="frameFilter">
                        <option value="">Tutti</option>
                        <option value="M">M</option>
                        <option value="S2">S2</option>
                        <option value="L">L</option>
                    </select>
                </div>
                <div class="filter-group">
                    <label>Anno</label>
                    <select id="yearFilter">
                        <option value="">Tutti</option>
                        <option value="2026">2026</option>
                        <option value="2025">2025</option>
                        <option value="2024">2024</option>
                        <option value="2023">2023</option>
                        <option value="2022">2022</option>
                        <option value="2021">2021</option>
                        <option value="2020">2020</option>
                        <option value="2019">2019</option>
                        <option value="2018">2018</option>
                    </select>
                </div>
                <div class="filter-group">
                    <label>Score min</label>
                    <input type="number" id="scoreMin" value="60" min="0" max="100">
                </div>
                <div class="filter-group">
                    <label>Stato</label>
                    <select id="statusFilter">
                        <option value="">Tutti</option>
                        <option value="active">Solo attivi</option>
                        <option value="rejected">Scartati</option>
                        <option value="sold">Venduti</option>
                    </select>
                </div>
                <div class="filter-group">
                    <label>&nbsp;</label>
                    <label class="filter-checkbox"><input type="checkbox" id="favOnly"> ⭐ Solo preferiti</label>
                </div>
                <div class="filter-group">
                    <label>&nbsp;</label>
                    <label class="filter-checkbox"><input type="checkbox" id="aiOnly"> 🤖 Solo con analisi AI</label>
                </div>
                <div class="filter-group">
                    <label>Ricerca testo libero</label>
                    <input type="text" id="textFilter" placeholder="Titolo, marca, modello...">
                </div>
            </div>
        </div>

        <h2 class="section-title">🏆 Top 10 Deals</h2>
        <div class="top-10">
"""

    for idx, bike in enumerate(top_10, 1):
        score_val = bike["score_total"] or 0
        analysis = _combine_analysis(bike) or "In attesa di valutazione"
        fav_prefix = "⭐ " if bike.get("is_favorite") else ""
        html += f"""            <div class="top-item">
                <div><span class="top-rank">{idx}</span>{fav_prefix}<a href="{bike['url']}" target="_blank">{bike['title']}</a> <span class="top-portal">({bike['portal']})</span></div>
                <div class="top-analysis">{analysis}</div>
                <div class="top-meta">{score_val:.1f} · {_format_price(bike)} · {bike['distance_km']:.1f} km</div>
            </div>
"""

    html += """        </div>

        <!-- Analysis Modal -->
        <div id="analysisModal" class="modal">
            <div class="modal-content">
                <div class="modal-header-actions">
                    <button class="modal-nav-btn" id="modalPrevBtn" onclick="navigateDetail(-1)" title="Annuncio precedente">←</button>
                    <button class="modal-nav-btn" id="modalNextBtn" onclick="navigateDetail(1)" title="Annuncio successivo">→</button>
                    <span class="modal-close" onclick="closeAnalysis()">&times;</span>
                </div>
                <h2 id="modalTitle"></h2>
                <div class="modal-body" id="modalBody"></div>
"""

    if interactive:
        html += """                <div class="edit-specs">
                    <h3>✏️ Correggi specifiche (es. hai riconosciuto il motore da una foto)</h3>
                    <div class="edit-fields">
                        <label>Marca motore <input type="text" id="editMotorBrand" placeholder="es. Bosch"></label>
                        <label>Modello motore <input type="text" id="editMotorModel" placeholder="es. Performance CX Gen4"></label>
                        <label>Coppia motore (Nm) <input type="number" id="editMotorTorque"></label>
                        <label>Batteria Wh <input type="number" id="editBattery"></label>
                        <label>Sospensioni <select id="editSuspension">
                            <option value="">— non specificato —</option>
                            <option value="full_suspension">Full suspension</option>
                            <option value="hardtail">Hardtail</option>
                            <option value="unknown">Non specificata</option>
                        </select></label>
                        <label>Taglia <input type="text" id="editFrame"></label>
                    </div>
                    <button class="btn-save" onclick="saveSpecs()">💾 Salva correzioni</button>
                </div>
                <div class="modal-actions">
                    <button class="btn-reject" onclick="rejectListing()">✕ Scarta</button>
                    <button class="btn-sold" onclick="markSold()">✅ Segna venduta</button>
                    <button class="btn-restore" onclick="restoreListing()">↩️ Ripristina attiva</button>
                </div>
"""

    html += """            </div>
        </div>

        <h2 class="section-title">📋 Tutti gli annunci</h2>
        <table id="table">
            <thead>
                <tr>
                    <th>Score</th>
                    <th>Annuncio</th>
                    <th>Prezzo</th>
                    <th>Status</th>
                    <th>Motore</th>
                    <th>Batteria</th>
                    <th>Sospensioni</th>
                    <th>Anno</th>
                    <th>Taglia</th>
                    <th>Distanza</th>
                    <th>Aggiunto</th>
                    <th>#</th>
                    <th class="no-sort">Azioni</th>
                </tr>
            </thead>
            <tbody id="tbody">
"""

    row_templates = []

    for idx, bike in enumerate(listings):
        score_val = bike["score_total"] or 0
        score_class = _score_class(score_val)

        status = bike["status"]
        status_class = (
            "new" if status == "NEW" else
            "price-drop" if status == "PRICE_DROP" else
            "sold" if status in ("SOLD", "DELISTED") else
            "rejected" if status == "REJECTED" else ""
        )
        # Bucket for the "Stato" filter — mirrors status_class's grouping.
        status_group = (
            "rejected" if status == "REJECTED" else
            "sold" if status in ("SOLD", "DELISTED") else
            "active"
        )

        motor_text = f"{bike['motor_brand']}" if bike["motor_brand"] else "N/A"
        if bike.get("motor_torque_nm"):
            motor_text += f" {bike['motor_torque_nm']:.0f}Nm"
        if bike.get("motor_verified") == 0:
            motor_text += " ⚠️ da verificare"

        battery_text = f"{bike['battery_capacity_wh']:.0f}Wh" if bike["battery_capacity_wh"] else "N/A"
        frame_text = bike["frame_size"] or "N/A"
        history = history_by_id.get(bike["id"], [])
        previous_price = _get_previous_price(history) if status == "PRICE_DROP" else None
        price_text = _format_price(bike, previous_price)
        anno_text = bike.get("model_year") or "N/A"
        km_text = f"{bike['odometer_km']:.0f} km" if bike.get("odometer_km") else "N/A"
        added_text = _format_date(bike.get("first_seen_at"))
        suspension_text = _SUSPENSION_LABELS.get(bike.get("suspension_type"), "N/A") if bike.get("suspension_type") else "N/A"
        meta_text = f"Taglia {frame_text} · {anno_text} · {km_text}"
        ai_icon = '<span class="ai-icon" title="Analisi AI disponibile">🤖</span> ' if bike.get("ai_analysis") else ''
        new_icon = '<span class="new-icon" title="Annuncio nuovo">🆕</span> ' if status == "NEW" else ''

        detail_html = _build_detail_html(bike, history)
        row_templates.append(f'<template data-listing-id="{_attr(bike["id"])}">{detail_html}</template>')
        is_favorite = bool(bike.get("is_favorite"))
        fav_prefix = "⭐ " if is_favorite else ""

        row_class = "sold" if status_group in ("sold", "rejected") else ""

        if interactive:
            star_btn = f'<button class="icon-btn icon-star" onclick="toggleFavorite(this)" title="Preferito">{"⭐" if is_favorite else "☆"}</button>'
            actions_cell = (
                '<div class="row-actions">'
                f'{star_btn}'
                '<button class="icon-btn icon-details" onclick="showAnalysis(this)" title="Dettagli e correzioni">📋</button>'
                '<button class="icon-btn icon-danger" onclick="rejectRow(this)" title="Scarta — non mi interessa">✕</button>'
                '<button class="icon-btn icon-success" onclick="soldRow(this)" title="Segna come venduta">✓</button>'
                '<button class="icon-btn icon-delete" onclick="deleteRow(this)" title="Cancella dalla lista">🗑️</button>'
                '</div>'
            )
            # Double-click-to-edit on the 4 columns that map to a correctable
            # spec field (see corrections.py::EDITABLE_SPEC_FIELDS) — quicker
            # than opening the full "Dettagli" modal for a single-field fix.
            motor_cell_attrs = ' class="editable-cell" ondblclick="editCell(this, \'motor\')" title="Doppio click per modificare"'
            battery_cell_attrs = ' class="editable-cell" ondblclick="editCell(this, \'battery\')" title="Doppio click per modificare"'
            suspension_cell_attrs = ' class="editable-cell" ondblclick="editCell(this, \'suspension\')" title="Doppio click per modificare"'
            frame_cell_attrs = ' class="editable-cell" ondblclick="editCell(this, \'frame\')" title="Doppio click per modificare"'
        else:
            actions_cell = '<button class="btn-details" onclick="showAnalysis(this)">📋 Dettagli</button>'
            motor_cell_attrs = battery_cell_attrs = suspension_cell_attrs = frame_cell_attrs = ''

        html += f"""                <tr class="{row_class}" data-id="{_attr(bike['id'])}" data-numeric-id="{bike['numeric_id']}" data-favorite="{1 if is_favorite else 0}" data-status-group="{status_group}" data-score="{bike.get('ranking_score') if bike.get('ranking_score') is not None else score_val}" data-price="{bike['price_chf']}" data-price-previous="{_attr(previous_price or '')}" data-distance="{bike['distance_km']}" data-motor="{motor_text}" data-motor-torque="{_attr(bike.get('motor_torque_nm'))}" data-battery="{bike['battery_capacity_wh'] or 0}" data-suspension="{_attr(bike.get('suspension_type'))}" data-frame="{frame_text}" data-year="{_attr(bike.get('model_year'))}" data-first-seen="{_attr(bike.get('first_seen_at'))}" data-has-ai="{1 if bike.get('ai_analysis') else 0}" data-edit-motor-brand="{_attr(bike.get('motor_brand'))}" data-edit-motor-model="{_attr(bike.get('motor_model'))}" data-edit-motor-torque="{_attr(bike.get('motor_torque_nm'))}" data-edit-battery="{_attr(bike.get('battery_capacity_wh'))}" data-edit-suspension="{_attr(bike.get('suspension_type'))}" data-edit-frame="{_attr(bike.get('frame_size'))}">
                    <td><span class="score {score_class}">{score_val:.1f}</span></td>
                    <td>
                        <a class="title-link" href="{bike['url']}" target="_blank">{fav_prefix}{bike['title'][:70]}</a>
                        <div class="title-meta">{new_icon}{ai_icon}{bike['portal']} · {meta_text}</div>
                    </td>
                    <td>{price_text}</td>
                    <td><span class="status {status_class}">{status}</span></td>
                    <td{motor_cell_attrs}><span class="motor">{motor_text}</span></td>
                    <td{battery_cell_attrs}>{battery_text}</td>
                    <td{suspension_cell_attrs}>{suspension_text}</td>
                    <td>{anno_text}</td>
                    <td{frame_cell_attrs}>{frame_text}</td>
                    <td>{bike['distance_km']:.1f} km</td>
                    <td>{added_text}</td>
                    <td class="numeric-id">#{bike['numeric_id']}</td>
                    <td>{actions_cell}</td>
                </tr>
"""

    html += """            </tbody>
        </table>
    </div>

    <div id="detailTemplates" style="display: none;">""" + "".join(row_templates) + """</div>

    <script>
        // Modal functions
        let currentListingId = null;

        function showAnalysis(button) {
            const row = button.closest('tr');
            currentListingId = row.getAttribute('data-id');
            const numericId = row.getAttribute('data-numeric-id');
            const title = row.querySelector('a').textContent;
            document.getElementById('modalTitle').textContent = `📋 #${numericId} · ${title}`;

            const modalBody = document.getElementById('modalBody');
            modalBody.innerHTML = '';
            const tpl = document.querySelector(`template[data-listing-id="${currentListingId}"]`);
            if (tpl) {
                modalBody.appendChild(tpl.content.cloneNode(true));
            }

            const motorBrandInput = document.getElementById('editMotorBrand');
            if (motorBrandInput) {
                motorBrandInput.value = row.getAttribute('data-edit-motor-brand') || '';
                document.getElementById('editMotorModel').value = row.getAttribute('data-edit-motor-model') || '';
                document.getElementById('editMotorTorque').value = row.getAttribute('data-edit-motor-torque') || '';
                document.getElementById('editBattery').value = row.getAttribute('data-edit-battery') || '';
                document.getElementById('editSuspension').value = row.getAttribute('data-edit-suspension') || '';
                document.getElementById('editFrame').value = row.getAttribute('data-edit-frame') || '';
            }

            document.getElementById('analysisModal').classList.add('show');
            // Lock the page behind the overlay so a wheel/trackpad scroll
            // always reaches the modal — without this, scrolling while the
            // mouse happens to sit over the dimmed backdrop (very easy once
            // you navigate with the arrow keys instead of clicking, since
            // the cursor never moves back over the modal) scrolled the
            // listing table behind it instead of the modal content.
            document.body.style.overflow = 'hidden';
            document.querySelector('.modal-content').scrollTop = 0;
            updateModalNavButtons();
        }

        function closeAnalysis() {
            document.getElementById('analysisModal').classList.remove('show');
            document.body.style.overflow = '';
        }

        // Prev/Next cycle through the currently *visible* rows (respecting
        // whatever filters are active) so navigation never jumps to a
        // listing you've filtered out — findable by clicking its own
        // "Dettagli" button, same as opening it normally.
        function getVisibleRows() {
            return Array.from(document.querySelectorAll('#tbody tr'))
                .filter(row => row.dataset.id && row.style.display !== 'none');
        }

        function navigateDetail(direction) {
            const rows = getVisibleRows();
            const idx = rows.findIndex(row => row.getAttribute('data-id') === currentListingId);
            const nextIdx = idx + direction;
            if (idx === -1 || nextIdx < 0 || nextIdx >= rows.length) return;
            const targetRow = rows[nextIdx];
            const detailBtn = targetRow.querySelector('.icon-details, .btn-details');
            if (detailBtn) showAnalysis(detailBtn);
        }

        function updateModalNavButtons() {
            const rows = getVisibleRows();
            const idx = rows.findIndex(row => row.getAttribute('data-id') === currentListingId);
            document.getElementById('modalPrevBtn').disabled = idx <= 0;
            document.getElementById('modalNextBtn').disabled = idx === -1 || idx >= rows.length - 1;
        }

        // Spec-correction actions — POST to server.py's API without reload,
        // so the modal stays open and you can make more edits.
        async function postActionNoReload(path, body) {
            try {
                const resp = await fetch(`/api/listings/${currentListingId}/${path}`, {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify(body || {})
                });
                if (!resp.ok) throw new Error(await resp.text());
                return await resp.json();
            } catch (e) {
                alert('Azione non riuscita. Assicurati di aver avviato il server locale (python3 server.py) e di aver aperto http://127.0.0.1:5050 — non il file index.html.\\n\\n' + e.message);
                return null;
            }
        }

        // Status/state-changing actions — POST to server.py's API and reload
        // so the page reflects the new DB state (status change, deletion, etc).
        async function postAction(path, body) {
            try {
                const resp = await fetch(`/api/listings/${currentListingId}/${path}`, {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify(body || {})
                });
                if (!resp.ok) throw new Error(await resp.text());
                location.reload();
            } catch (e) {
                alert('Azione non riuscita. Assicurati di aver avviato il server locale (python3 server.py) e di aver aperto http://127.0.0.1:5050 — non il file index.html.\\n\\n' + e.message);
            }
        }

        function rejectListing() {
            if (confirm('Scartare questo annuncio?')) postAction('reject');
        }

        function markSold() {
            if (confirm('Segnare questo annuncio come venduto?')) postAction('sold');
        }

        function restoreListing() {
            postAction('restore');
        }

        // Row-level actions (favorite/reject/sold) — clicked directly from a
        // table row's own buttons, not through the modal, so each reads the
        // listing id off its own row rather than the shared currentListingId.
        async function postRowAction(button, path) {
            const listingId = button.closest('tr').getAttribute('data-id');
            try {
                const resp = await fetch(`/api/listings/${listingId}/${path}`, {method: 'POST'});
                if (!resp.ok) throw new Error(await resp.text());
                location.reload();
            } catch (e) {
                alert('Azione non riuscita. Assicurati di aver avviato il server locale (python3 server.py).\\n\\n' + e.message);
            }
        }

        function toggleFavorite(button) {
            postRowAction(button, 'favorite');
        }

        function rejectRow(button) {
            if (confirm('Scartare questo annuncio?')) postRowAction(button, 'reject');
        }

        function soldRow(button) {
            if (confirm('Segnare questo annuncio come venduto?')) postRowAction(button, 'sold');
        }

        function deleteRow(button) {
            if (confirm('Cancellare definitivamente questo annuncio dalla lista? Azione irreversibile.')) postRowAction(button, 'delete');
        }

        async function saveSpecs() {
            const torque = document.getElementById('editMotorTorque').value;
            const battery = document.getElementById('editBattery').value;
            const result = await postActionNoReload('specs', {
                motor_brand: document.getElementById('editMotorBrand').value || null,
                motor_model: document.getElementById('editMotorModel').value || null,
                motor_torque_nm: torque !== '' ? parseFloat(torque) : null,
                battery_capacity_wh: battery !== '' ? parseFloat(battery) : null,
                suspension_type: document.getElementById('editSuspension').value || null,
                frame_size: document.getElementById('editFrame').value || null
            });
            if (result) {
                alert('✓ Specifiche salvate.');
            }
        }

        // Inline cell editing — double-click a Motore/Batteria/Sospensioni/
        // Taglia cell to edit it in place, without opening the full
        // "Dettagli" modal. ✓ saves (POSTs just that field to the same
        // /specs endpoint saveSpecs() uses) and reloads; ✕ restores the
        // cell's original content with no request.
        const SUSPENSION_OPTIONS = [
            ['unknown', 'Non specificata'],
            ['full_suspension', 'Full suspension'],
            ['hardtail', 'Hardtail']
        ];

        function editCell(td, field) {
            if (td.classList.contains('editing')) return;
            const row = td.closest('tr');
            td.dataset.original = td.innerHTML;
            td.classList.add('editing');

            let inputHtml = '';
            if (field === 'battery') {
                const val = row.getAttribute('data-edit-battery') || '';
                inputHtml = `<input type="number" class="cell-edit-input" id="cellEdit_battery" value="${val}">`;
            } else if (field === 'suspension') {
                const val = row.getAttribute('data-edit-suspension') || '';
                inputHtml = '<select class="cell-edit-input" id="cellEdit_suspension">' +
                    SUSPENSION_OPTIONS.map(([v, l]) => `<option value="${v}"${v === val ? ' selected' : ''}>${l}</option>`).join('') +
                    '</select>';
            } else if (field === 'frame') {
                const val = row.getAttribute('data-edit-frame') || '';
                inputHtml = `<input type="text" class="cell-edit-input" id="cellEdit_frame" value="${val}">`;
            } else if (field === 'motor') {
                const brand = row.getAttribute('data-edit-motor-brand') || '';
                const model = row.getAttribute('data-edit-motor-model') || '';
                const torque = row.getAttribute('data-edit-motor-torque') || '';
                inputHtml =
                    `<input type="text" class="cell-edit-input" id="cellEdit_motor_brand" placeholder="Marca" value="${brand}">` +
                    `<input type="text" class="cell-edit-input" id="cellEdit_motor_model" placeholder="Modello" value="${model}">` +
                    `<input type="number" class="cell-edit-input" id="cellEdit_motor_torque" placeholder="Nm" value="${torque}">`;
            }

            td.innerHTML = `<div class="cell-edit">${inputHtml}<span class="cell-edit-actions">` +
                `<button class="cell-edit-btn cell-edit-save" onclick="saveCell(this, '${field}')" title="Salva">✓</button>` +
                `<button class="cell-edit-btn cell-edit-cancel" onclick="cancelCell(this)" title="Annulla">✕</button>` +
                '</span></div>';

            const firstInput = td.querySelector('input, select');
            if (firstInput) firstInput.focus();
        }

        function cancelCell(button) {
            const td = button.closest('td');
            td.innerHTML = td.dataset.original;
            td.classList.remove('editing');
        }

        async function saveCell(button, field) {
            const td = button.closest('td');
            const row = td.closest('tr');
            const listingId = row.getAttribute('data-id');

            const payload = {};
            let newValue = null;
            if (field === 'battery') {
                const v = document.getElementById('cellEdit_battery').value;
                payload.battery_capacity_wh = v !== '' ? parseFloat(v) : null;
                newValue = v !== '' ? `${parseFloat(v).toFixed(0)}Wh` : 'N/A';
            } else if (field === 'suspension') {
                payload.suspension_type = document.getElementById('cellEdit_suspension').value || null;
                const val = document.getElementById('cellEdit_suspension').value;
                newValue = val === 'full_suspension' ? 'Full suspension' : val === 'hardtail' ? 'Hardtail' : 'Non specificata';
            } else if (field === 'frame') {
                payload.frame_size = document.getElementById('cellEdit_frame').value || null;
                newValue = document.getElementById('cellEdit_frame').value || 'N/A';
            } else if (field === 'motor') {
                const torque = document.getElementById('cellEdit_motor_torque').value;
                payload.motor_brand = document.getElementById('cellEdit_motor_brand').value || null;
                payload.motor_model = document.getElementById('cellEdit_motor_model').value || null;
                payload.motor_torque_nm = torque !== '' ? parseFloat(torque) : null;
                const brand = payload.motor_brand || '';
                const torqueStr = payload.motor_torque_nm ? ` ${payload.motor_torque_nm.toFixed(0)}Nm` : '';
                newValue = (brand + torqueStr).trim() || 'N/A';
            }

            try {
                const resp = await fetch(`/api/listings/${listingId}/specs`, {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify(payload)
                });
                if (!resp.ok) throw new Error(await resp.text());

                // Update row attributes and display without full reload
                if (field === 'battery') {
                    row.setAttribute('data-edit-battery', payload.battery_capacity_wh || '');
                    row.setAttribute('data-battery', payload.battery_capacity_wh || 0);
                } else if (field === 'suspension') {
                    row.setAttribute('data-edit-suspension', payload.suspension_type || '');
                    row.setAttribute('data-suspension', payload.suspension_type || 'unknown');
                } else if (field === 'frame') {
                    row.setAttribute('data-edit-frame', payload.frame_size || '');
                    row.setAttribute('data-frame', payload.frame_size || 'N/A');
                } else if (field === 'motor') {
                    row.setAttribute('data-edit-motor-brand', payload.motor_brand || '');
                    row.setAttribute('data-edit-motor-model', payload.motor_model || '');
                    row.setAttribute('data-edit-motor-torque', payload.motor_torque_nm || '');
                    row.setAttribute('data-motor-torque', payload.motor_torque_nm || '');
                    row.setAttribute('data-motor', newValue);
                }

                td.innerHTML = newValue;
                td.classList.remove('editing');
            } catch (e) {
                alert('Salvataggio non riuscito. Assicurati di aver avviato il server locale (python3 server.py).\\n\\n' + e.message);
            }
        }

        // ESC closes, arrow keys navigate — only while the modal is open
        // and not while typing in one of the edit-specs fields.
        document.addEventListener('keydown', (e) => {
            const modalOpen = document.getElementById('analysisModal').classList.contains('show');
            if (!modalOpen) return;
            if (e.key === 'Escape') { closeAnalysis(); return; }
            const typing = ['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement.tagName);
            if (typing) return;
            if (e.key === 'ArrowLeft') navigateDetail(-1);
            if (e.key === 'ArrowRight') navigateDetail(1);
        });

        // Close modal on background click
        document.getElementById('analysisModal').addEventListener('click', (e) => {
            if (e.target.id === 'analysisModal') closeAnalysis();
        });

        const priceMinInput = document.getElementById('priceMin');
        const priceMaxInput = document.getElementById('priceMax');
        const priceMinVal = document.getElementById('priceMinVal');
        const priceMaxVal = document.getElementById('priceMaxVal');

        async function updateTop10() {
            const params = new URLSearchParams({
                price_min: priceMinInput.value,
                price_max: priceMaxInput.value,
                dist_max: document.getElementById('distMax').value || undefined,
                motor_brand: document.getElementById('motorFilter').value || undefined,
                battery_min: document.getElementById('batteryMin').value || undefined,
                frame_size: document.getElementById('frameFilter').value || undefined,
                year: document.getElementById('yearFilter').value || undefined,
                score_min: document.getElementById('scoreMin').value,
                status: document.getElementById('statusFilter').value || undefined,
                fav_only: document.getElementById('favOnly').checked,
                ai_only: document.getElementById('aiOnly').checked,
                limit: 10
            });

            try {
                const response = await fetch(`/api/top-deals?${params}`);
                if (!response.ok) throw new Error('Network response not ok');
                const deals = await response.json();
                renderTop10(deals);
            } catch (error) {
                console.error('Errore caricamento top 10:', error);
            }
        }

        function renderTop10(deals) {
            const topContainer = document.querySelector('.top-10');
            if (!topContainer) return;

            topContainer.innerHTML = '';

            if (deals.length === 0) {
                topContainer.innerHTML = '<div style="grid-column: 1/-1; text-align: center; padding: 40px; color: #999;">Nessun annuncio corrisponde ai filtri selezionati</div>';
                return;
            }

            deals.forEach((deal, idx) => {
                const item = document.createElement('div');
                item.className = 'top-item';
                const rankBadge = idx + 1;
                const link = deal.url || '#';
                const title = deal.title || 'Unknown';
                const portal = deal.portal || 'unknown';
                const score = deal.ranking_score ? deal.ranking_score.toFixed(1) : deal.score_total?.toFixed(1) || 'N/A';
                const price = deal.price_raw ? `${deal.price_raw.toFixed(0)} ${deal.currency || 'CHF'}` : `${deal.price_chf?.toFixed(0) || 'N/A'} CHF`;
                const distance = deal.distance_km ? deal.distance_km.toFixed(1) : 'N/A';

                item.innerHTML = `
                    <div>
                        <span class="top-rank">${rankBadge}</span>
                        <a href="${link}" target="_blank">${title}</a>
                        <span class="top-portal">(${portal})</span>
                    </div>
                    <div class="top-analysis">${deal.user_analysis || 'Nessuna analisi disponibile'}</div>
                    <div class="top-meta">${score} · ${price} · ${distance} km</div>
                `;

                topContainer.appendChild(item);
            });
        }

        function applyFilters() {
            filterTable();
            updateTop10();
        }

        priceMinInput.addEventListener('input', () => {
            priceMinVal.textContent = priceMinInput.value;
            applyFilters();
        });
        priceMaxInput.addEventListener('input', () => {
            priceMaxVal.textContent = priceMaxInput.value;
            applyFilters();
        });

        document.getElementById('distMax').addEventListener('input', applyFilters);
        document.getElementById('motorFilter').addEventListener('change', applyFilters);
        document.getElementById('batteryMin').addEventListener('input', applyFilters);
        document.getElementById('frameFilter').addEventListener('change', applyFilters);
        document.getElementById('yearFilter').addEventListener('change', applyFilters);
        document.getElementById('scoreMin').addEventListener('input', applyFilters);
        document.getElementById('favOnly').addEventListener('change', applyFilters);
        document.getElementById('aiOnly').addEventListener('change', applyFilters);
        document.getElementById('statusFilter').addEventListener('change', applyFilters);

        // Text filter with debounce
        let textFilterTimeout;
        document.getElementById('textFilter').addEventListener('input', function() {
            clearTimeout(textFilterTimeout);
            textFilterTimeout = setTimeout(applyFilters, 300);
        });

        function filterTable() {
            const priceMin = parseFloat(priceMinInput.value);
            const priceMax = parseFloat(priceMaxInput.value);
            const distMax = parseFloat(document.getElementById('distMax').value);
            const motorFilter = document.getElementById('motorFilter').value;
            const batteryMin = parseFloat(document.getElementById('batteryMin').value);
            const frameFilter = document.getElementById('frameFilter').value;
            const yearFilter = document.getElementById('yearFilter').value;
            const scoreMin = parseFloat(document.getElementById('scoreMin').value);
            const favOnly = document.getElementById('favOnly').checked;
            const aiOnly = document.getElementById('aiOnly').checked;
            const statusFilter = document.getElementById('statusFilter').value;
            const textFilter = document.getElementById('textFilter').value.toLowerCase();

            const rows = document.querySelectorAll('#tbody tr');
            let visibleCount = 0;

            rows.forEach(row => {
                const price = parseFloat(row.dataset.price);
                const distance = parseFloat(row.dataset.distance);
                const motor = row.dataset.motor;
                const battery = parseFloat(row.dataset.battery);
                const frame = row.dataset.frame;
                const year = row.dataset.year;
                const score = parseFloat(row.dataset.score);
                const favorite = row.dataset.favorite === '1';
                const hasAi = row.dataset.hasAi === '1';
                const statusGroup = row.dataset.statusGroup;
                const titleText = row.querySelector('a.title-link').textContent.toLowerCase();

                let show = true;
                if (priceMin > 0 && price < priceMin) show = false;
                if (price > priceMax) show = false;
                if (distance > distMax) show = false;
                if (motorFilter && !motor.includes(motorFilter)) show = false;
                if (battery < batteryMin) show = false;
                if (frameFilter && frame !== frameFilter) show = false;
                if (yearFilter && year !== yearFilter) show = false;
                if (score < scoreMin) show = false;
                if (favOnly && !favorite) show = false;
                if (aiOnly && !hasAi) show = false;
                if (statusFilter && statusGroup !== statusFilter) show = false;
                if (textFilter && !titleText.includes(textFilter)) show = false;

                row.style.display = show ? '' : 'none';
                if (show) visibleCount++;
                saveFilters();
            });

            const tbody = document.getElementById('tbody');
            let info = tbody.querySelector('.filter-info');
            if (info) info.remove();

            if (visibleCount === 0) {
                const noResult = document.createElement('tr');
                noResult.className = 'filter-info';
                noResult.innerHTML = '<td colspan="13" style="text-align: center; padding: 20px; color: #999;">Nessun risultato con questi filtri</td>';
                tbody.appendChild(noResult);
            }
        }

        function resetFilters() {
            // "Reset" must mean "show everything again", not "reapply the
            // typical 1500-3000/60+/400Wh+ starting range" — it used to set
            // those same restrictive defaults and then filter by them,
            // which silently hid every listing outside that range (looked
            // like most of the list had vanished). Use each input's own
            // min/max bounds so nothing is excluded.
            priceMinInput.value = priceMinInput.min;
            priceMaxInput.value = priceMaxInput.max;
            priceMinVal.textContent = priceMinInput.value;
            priceMaxVal.textContent = priceMaxInput.value;
            document.getElementById('distMax').value = document.getElementById('distMax').max;
            document.getElementById('motorFilter').value = '';
            document.getElementById('batteryMin').value = 0;
            document.getElementById('frameFilter').value = '';
            document.getElementById('yearFilter').value = '';
            document.getElementById('scoreMin').value = 0;
            document.getElementById('favOnly').checked = false;
            document.getElementById('aiOnly').checked = false;
            document.getElementById('statusFilter').value = '';
            document.getElementById('textFilter').value = '';
            saveFilters();
            applyFilters();
        }

        function saveFilters() {
            const filters = {
                priceMin: priceMinInput.value,
                priceMax: priceMaxInput.value,
                distMax: document.getElementById('distMax').value,
                motorFilter: document.getElementById('motorFilter').value,
                batteryMin: document.getElementById('batteryMin').value,
                frameFilter: document.getElementById('frameFilter').value,
                yearFilter: document.getElementById('yearFilter').value,
                scoreMin: document.getElementById('scoreMin').value,
                favOnly: document.getElementById('favOnly').checked,
                aiOnly: document.getElementById('aiOnly').checked,
                statusFilter: document.getElementById('statusFilter').value,
                textFilter: document.getElementById('textFilter').value
            };
            localStorage.setItem('ebike-filters', JSON.stringify(filters));
        }

        function restoreFilters() {
            const saved = localStorage.getItem('ebike-filters');
            if (!saved) return;
            try {
                const filters = JSON.parse(saved);
                priceMinInput.value = filters.priceMin;
                priceMaxInput.value = filters.priceMax;
                priceMinVal.textContent = filters.priceMin;
                priceMaxVal.textContent = filters.priceMax;
                document.getElementById('distMax').value = filters.distMax;
                document.getElementById('motorFilter').value = filters.motorFilter;
                document.getElementById('batteryMin').value = filters.batteryMin;
                document.getElementById('frameFilter').value = filters.frameFilter;
                document.getElementById('yearFilter').value = filters.yearFilter;
                document.getElementById('scoreMin').value = filters.scoreMin;
                document.getElementById('favOnly').checked = filters.favOnly;
                document.getElementById('aiOnly').checked = filters.aiOnly;
                document.getElementById('statusFilter').value = filters.statusFilter;
                document.getElementById('textFilter').value = filters.textFilter || '';
                filterTable();
            } catch (e) {
                console.error('Errore ripristino filtri:', e);
            }
        }

        // Ripristina filtri al caricamento pagina
        window.addEventListener('DOMContentLoaded', restoreFilters);

        // Click-to-sort columns. One accessor per <th>, in the same order
        // as the header row — null marks a non-sortable column (Azioni).
        // Missing values (no year, never scored, etc.) always sort to the
        // bottom regardless of direction, instead of landing at whichever
        // end NaN/undefined happens to compare to.
        const SORT_COLUMNS = [
            row => parseFloat(row.dataset.score),
            { text: row => (row.querySelector('a.title-link')?.textContent || '').toLowerCase() },
            row => parseFloat(row.dataset.price),
            { text: row => row.dataset.statusGroup || '' },
            row => parseFloat(row.dataset.motorTorque),
            row => parseFloat(row.dataset.battery),
            { text: row => row.dataset.suspension || 'N/A' },
            row => parseInt(row.dataset.year, 10),
            { text: row => row.dataset.frame || 'N/A' },
            row => parseFloat(row.dataset.distance),
            row => row.dataset.firstSeen ? new Date(row.dataset.firstSeen).getTime() : NaN,
            row => parseInt(row.dataset.numericId, 10),
            null,
        ];

        let sortState = { index: null, dir: 1 };

        function sortTable(colIndex) {
            const column = SORT_COLUMNS[colIndex];
            if (!column) return;
            const isText = typeof column === 'object';
            const getValue = isText ? column.text : column;

            const dir = (sortState.index === colIndex) ? -sortState.dir : 1;
            sortState = { index: colIndex, dir };

            const tbody = document.getElementById('tbody');
            const rows = Array.from(tbody.querySelectorAll('tr[data-id]'));

            rows.sort((a, b) => {
                const va = getValue(a);
                const vb = getValue(b);
                const aMissing = isText ? !va : (va === null || Number.isNaN(va));
                const bMissing = isText ? !vb : (vb === null || Number.isNaN(vb));
                if (aMissing && bMissing) return 0;
                if (aMissing) return 1;
                if (bMissing) return -1;
                if (isText) return va < vb ? -dir : va > vb ? dir : 0;
                return (va - vb) * dir;
            });

            rows.forEach(row => tbody.appendChild(row));

            document.querySelectorAll('#table thead th').forEach((th, i) => {
                th.classList.remove('sorted-asc', 'sorted-desc');
                if (i === colIndex) th.classList.add(dir === 1 ? 'sorted-asc' : 'sorted-desc');
            });
        }

        document.querySelectorAll('#table thead th').forEach((th, i) => {
            if (!SORT_COLUMNS[i]) return;
            th.addEventListener('click', () => sortTable(i));
        });

        const backToTopBtn = document.getElementById('backToTop');
        window.addEventListener('scroll', () => {
            backToTopBtn.classList.toggle('visible', window.scrollY > 400);
        });
        backToTopBtn.addEventListener('click', () => {
            window.scrollTo({ top: 0, behavior: 'smooth' });
        });
    </script>
</body>
</html>
"""

    return html


def generate_dashboard(db_path: str, output_path: str = "index.html"):
    """Write the (read-only, non-interactive) dashboard snapshot to disk.
    Used by run.py and analyze.py after each scan/analysis pass."""
    html = render_dashboard_html(db_path, interactive=False)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"✓ Dashboard generated: {output_path}")


if __name__ == "__main__":
    import os
    config_path = Path(__file__).parent.parent / "config" / "config.yaml"
    with open(config_path) as f:
        config = yaml.safe_load(f)

    db_path = config["app"]["db_path"]
    output = Path(__file__).parent.parent / "index.html"

    generate_dashboard(db_path, str(output))
