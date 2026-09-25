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


def _format_price(bike: dict) -> str:
    """Show the price in the currency the listing was actually posted in —
    not silently converted to CHF. Scoring/filtering still use price_chf
    internally; this only changes what's displayed. A small "(~X CHF)" hint
    is appended for non-CHF listings since the budget filters are CHF-based."""
    price_raw = bike.get("price_raw")
    currency = (bike.get("currency") or "").upper()
    price_chf = bike.get("price_chf")
    if price_raw is None:
        return f"{price_chf:.0f} CHF" if price_chf is not None else "N/A"
    text = f"{price_raw:.0f} {currency}".strip()
    if currency and currency != "CHF" and price_chf is not None:
        text += f" (~{price_chf:.0f} CHF)"
    return text


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


def _build_spec_table_html(bike: dict) -> str:
    motor_bits = [b for b in (bike.get("motor_brand"), bike.get("motor_model")) if b]
    motor_text = _attr(" ".join(motor_bits)) if motor_bits else "N/A"
    if bike.get("motor_torque_nm"):
        motor_text += f" · {bike['motor_torque_nm']:.0f} Nm"
    if bike.get("motor_brand"):
        motor_text += (
            ' <span class="badge badge-warn">⚠️ da verificare</span>'
            if bike.get("motor_verified") == 0
            else ' <span class="badge badge-ok">✓ verificato</span>'
        )

    suspension_text = _SUSPENSION_LABELS.get(bike.get("suspension_type"), _attr(bike.get("suspension_type")) or "N/A")
    if bike.get("travel_front_mm"):
        suspension_text += f" · {bike['travel_front_mm']:.0f}mm"

    rows = [
        ("Motore", motor_text),
        ("Batteria", f"{bike['battery_capacity_wh']:.0f} Wh" if bike.get("battery_capacity_wh") else "N/A"),
        ("Taglia", _attr(bike.get("frame_size")) or "N/A"),
        ("Anno modello", bike.get("model_year") or "N/A"),
        ("Percorrenza", f"{bike['odometer_km']:.0f} km" if bike.get("odometer_km") else "N/A"),
        ("Sospensione", suspension_text),
        ("Freni", _BRAKES_LABELS.get(bike.get("brakes_tier"), _attr(bike.get("brakes_tier")) or "N/A")),
    ]
    rows_html = "".join(f"<tr><td>{label}</td><td>{value}</td></tr>" for label, value in rows)
    return f'<div class="detail-section"><h3>⚙️ Specifiche</h3><table class="spec-table">{rows_html}</table></div>'


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
    return f'<div class="detail-section"><h3>📊 Punteggio euristico — {total:.0f}/100</h3>{rows_html}</div>'


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
    backslash-n in the page instead of line breaks)."""
    sections = [
        f'<div class="detail-section"><h3>💰 Prezzo</h3>'
        f'<p class="detail-price">{_attr(_format_price(bike))}</p>'
        f'<p class="detail-sub">Visto la prima volta il {_format_date(bike.get("first_seen_at"))}</p></div>',
        _build_price_history_html(history),
        _build_spec_table_html(bike),
        _build_red_flags_html(bike),
        _build_score_breakdown_html(bike),
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

    return "".join(s for s in sections if s)


def render_dashboard_html(db_path: str, interactive: bool = False, show_all: bool = False) -> str:
    """Build the dashboard HTML from the DB.

    interactive=True renders the reject/mark-sold/restore buttons and the
    spec-correction form, wired to POST /api/listings/<id>/... — only
    meaningful when served by server.py, since a static file:// page has
    nothing to send those requests to. generate_dashboard() below always
    calls this with interactive=False so the auto-regenerated index.html
    (written by run.py/analyze.py) stays a plain read-only snapshot.

    show_all=True drops the ACTIVE/NEW/PRICE_DROP + rejection_reason filter
    so manually rejected/sold listings are visible again — otherwise, once
    set_manual_status() removes a listing from that filter, there would be
    no way to find it again to hit "restore".
    """
    db = Database(db_path)

    cursor = db.conn.cursor()
    where_clause = "1=1" if show_all else "l.status IN ('ACTIVE', 'NEW', 'PRICE_DROP') AND l.rejection_reason IS NULL"
    cursor.execute(f"""
    SELECT
        l.id, l.portal, l.title, l.price_raw, l.currency, l.price_chf, l.distance_km, l.url,
        l.first_seen_at, l.last_seen_at, l.status, l.is_favorite,
        l.user_analysis, l.ai_analysis, l.ai_score,
        s.motor_brand, s.motor_model, s.motor_torque_nm, s.motor_verified,
        s.battery_capacity_wh, s.frame_size, s.model_year, s.odometer_km,
        s.travel_front_mm, s.brakes_tier, s.suspension_type,
        s.has_red_flag, s.red_flag_details,
        sc.score_total, sc.score_price_value, sc.score_component_quality,
        sc.score_condition_mileage, sc.score_location_proximity, sc.score_fit_geometry
    FROM listings l
    LEFT JOIN specifications s ON l.id = s.listing_id
    LEFT JOIN scores sc ON l.id = sc.listing_id
    WHERE {where_clause}
    ORDER BY l.is_favorite DESC, COALESCE(sc.score_total, 0) DESC, l.price_chf ASC
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

    # Generate HTML
    html = f"""<!DOCTYPE html>
<html lang="it">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>E-Bike Hunter Dashboard</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #f5f5f5; color: #333; }}
        .container {{ max-width: 1400px; margin: 0 auto; padding: 20px; }}
        h1 {{ margin: 20px 0 10px; font-size: 24px; }}
        .meta {{ color: #666; font-size: 13px; margin-bottom: 20px; }}

        .filters {{ background: white; padding: 15px; border-radius: 8px; margin-bottom: 20px; display: flex; gap: 15px; flex-wrap: wrap; align-items: center; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
        .filter-group {{ display: flex; flex-direction: column; gap: 5px; }}
        .filter-group label {{ font-size: 12px; font-weight: 600; color: #666; }}
        .filter-group input, .filter-group select {{ padding: 6px 10px; border: 1px solid #ddd; border-radius: 4px; font-size: 13px; }}
        .filter-group input:focus, .filter-group select:focus {{ outline: none; border-color: #1976d2; background: #f0f8ff; }}

        table {{ width: 100%; border-collapse: collapse; background: white; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
        th {{ background: #1976d2; color: white; padding: 12px; text-align: left; font-weight: 600; font-size: 13px; }}
        td {{ padding: 10px 12px; border-bottom: 1px solid #eee; font-size: 13px; }}
        tr:hover {{ background: #f9f9f9; }}

        .score {{ font-weight: 600; background: #e3f2fd; padding: 4px 8px; border-radius: 4px; }}
        .score.high {{ background: #c8e6c9; color: #1b5e20; }}
        .score.mid {{ background: #fff9c4; color: #f57f17; }}
        .score.low {{ background: #ffccbc; color: #bf360c; }}

        .status {{ padding: 3px 8px; border-radius: 3px; font-size: 11px; font-weight: 600; }}
        .status.new {{ background: #bbdefb; color: #01579b; }}
        .status.price-drop {{ background: #f8bbd0; color: #880e4f; }}
        .status.sold {{ background: #ccc; color: #555; text-decoration: line-through; }}
        .status.rejected {{ background: #ffcdd2; color: #b71c1c; }}

        .motor {{ background: #f0f0f0; padding: 2px 6px; border-radius: 3px; font-size: 12px; }}

        a {{ color: #1976d2; text-decoration: none; }}
        a:hover {{ text-decoration: underline; }}

        .top-10 {{ background: white; padding: 20px; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
        .top-item {{ padding: 12px; border-bottom: 1px solid #eee; }}
        .top-item:last-child {{ border-bottom: none; }}
        .top-title {{ font-weight: 600; margin-bottom: 4px; }}
        .top-analysis {{ font-size: 12px; color: #555; font-style: italic; }}
        .top-meta {{ font-size: 11px; color: #999; margin-top: 4px; }}

        .sold {{ opacity: 0.5; }}

        .modal {{ display: none; position: fixed; z-index: 1000; left: 0; top: 0; width: 100%; height: 100%; background-color: rgba(0,0,0,0.5); }}
        .modal.show {{ display: block; }}
        .modal-content {{ background-color: white; margin: 5% auto; padding: 20px; border-radius: 8px; width: 80%; max-width: 900px; max-height: 80vh; overflow-y: auto; box-shadow: 0 4px 6px rgba(0,0,0,0.3); }}
        .modal-close {{ float: right; font-size: 24px; font-weight: bold; cursor: pointer; color: #999; }}
        .modal-close:hover {{ color: #333; }}
        .modal h2 {{ margin-top: 0; }}
        .modal-body {{ font-size: 14px; line-height: 1.6; }}

        .detail-section {{ margin-bottom: 18px; padding-bottom: 18px; border-bottom: 1px solid #eee; }}
        .detail-section:last-child {{ border-bottom: none; margin-bottom: 0; padding-bottom: 0; }}
        .detail-section h3 {{ font-size: 14px; margin-bottom: 10px; color: #1976d2; }}
        .detail-section p {{ margin: 6px 0; }}
        .detail-section ul {{ margin: 6px 0 6px 20px; }}
        .detail-price {{ font-size: 20px; font-weight: 700; }}
        .detail-sub {{ font-size: 12px; color: #888; }}
        .detail-text {{ font-size: 14px; }}
        .detail-warning {{ background: #fff3e0; border-radius: 6px; padding: 12px 15px; border-bottom: none; }}
        .detail-warning h3 {{ color: #e65100; }}
        .detail-ai {{ background: #f3f7fd; border-radius: 6px; padding: 12px 15px; border-bottom: none; }}

        .spec-table {{ width: 100%; border-collapse: collapse; box-shadow: none; }}
        .spec-table td {{ padding: 6px 8px; border-bottom: 1px solid #f0f0f0; font-size: 13px; }}
        .spec-table td:first-child {{ color: #888; width: 40%; }}

        .price-history {{ display: flex; flex-wrap: wrap; align-items: center; gap: 6px; }}
        .price-chip {{ background: #f0f0f0; border-radius: 6px; padding: 6px 10px; font-size: 13px; font-weight: 600; display: flex; flex-direction: column; align-items: center; }}
        .price-chip small {{ font-weight: normal; color: #888; font-size: 11px; }}
        .price-arrow {{ color: #999; }}

        .badge {{ display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: 11px; font-weight: 600; }}
        .badge-ok {{ background: #c8e6c9; color: #1b5e20; }}
        .badge-warn {{ background: #ffe0b2; color: #e65100; }}
        .badge-ai {{ background: #d1c4e9; color: #4527a0; }}

        .score-row {{ display: flex; align-items: center; gap: 10px; margin: 6px 0; font-size: 12px; }}
        .score-row-label {{ width: 140px; color: #666; flex-shrink: 0; }}
        .score-track {{ flex: 1; background: #eee; border-radius: 4px; height: 8px; overflow: hidden; }}
        .score-fill {{ background: #1976d2; height: 100%; }}
        .score-row-value {{ width: 28px; text-align: right; font-weight: 600; flex-shrink: 0; }}

        .btn-analysis {{ padding: 4px 8px; background: #1976d2; color: white; border: none; border-radius: 3px; cursor: pointer; font-size: 11px; font-weight: 600; }}
        .btn-analysis:hover {{ background: #1565c0; }}

        .row-actions {{ display: flex; gap: 4px; }}
        .btn-reject-sm {{ padding: 4px 8px; background: #f44336; color: white; border: none; border-radius: 3px; cursor: pointer; font-size: 11px; font-weight: 600; }}
        .btn-sold-sm {{ padding: 4px 8px; background: #757575; color: white; border: none; border-radius: 3px; cursor: pointer; font-size: 11px; font-weight: 600; }}

        .btn-reject {{ padding: 6px 12px; background: #f44336; color: white; border: none; border-radius: 4px; cursor: pointer; font-size: 12px; font-weight: 600; }}
        .btn-sold {{ padding: 6px 12px; background: #757575; color: white; border: none; border-radius: 4px; cursor: pointer; font-size: 12px; font-weight: 600; }}
        .btn-restore {{ padding: 6px 12px; background: #1976d2; color: white; border: none; border-radius: 4px; cursor: pointer; font-size: 12px; font-weight: 600; }}
        .btn-favorite {{ padding: 6px 12px; background: #f9a825; color: white; border: none; border-radius: 4px; cursor: pointer; font-size: 12px; font-weight: 600; }}
        .btn-save {{ padding: 6px 12px; background: #2e7d32; color: white; border: none; border-radius: 4px; cursor: pointer; font-size: 12px; font-weight: 600; }}
        .modal-actions {{ margin-top: 15px; padding-top: 15px; border-top: 1px solid #eee; display: flex; gap: 8px; }}
        .edit-specs {{ margin-top: 15px; padding-top: 15px; border-top: 1px solid #eee; }}
        .edit-specs h3 {{ font-size: 14px; margin-bottom: 10px; }}
        .edit-specs .edit-fields {{ display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 10px; }}
        .edit-specs label {{ display: flex; flex-direction: column; gap: 3px; font-size: 11px; font-weight: 600; color: #666; }}
        .edit-specs input {{ padding: 6px 8px; border: 1px solid #ddd; border-radius: 4px; font-size: 13px; }}
        .star-btn {{ background: none; border: none; cursor: pointer; font-size: 16px; padding: 0; }}
        .readonly-banner {{ background: #fff3cd; color: #7a5b00; padding: 10px 15px; border-radius: 6px; margin-bottom: 15px; font-size: 13px; }}
        .readonly-banner code {{ background: rgba(0,0,0,0.08); padding: 1px 5px; border-radius: 3px; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>🚲 E-Bike Hunter Dashboard</h1>
        <div class="meta">Aggiornato: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | {len(listings)} annunci trovati{' (tutti gli stati)' if show_all else ''}</div>
        <div class="meta">⚠️ Portali bloccati (controllo manuale): <a href="https://www.decathlon.ch/search?from=0&size=40" target="_blank">Decathlon.ch</a> (Cloudflare)</div>
        {'<div class="meta"><a href="/">← Nascondi scartate/vendute</a></div>' if interactive and show_all else ''}
        {'<div class="meta"><a href="/?all=1">Mostra anche scartate/vendute →</a></div>' if interactive and not show_all else ''}
        {'<div class="readonly-banner">📄 Questa è una copia statica, sola lettura (generata da <code>run.py</code>/<code>analyze.py</code>/<code>generate_dashboard.py</code>). Per scartare, segnare venduta/preferita o correggere le specifiche a mano, avvia <code>python3 server.py</code> invece di aprire questo file.</div>' if not interactive else ''}

        <div class="filters">
            <div class="filter-group">
                <label>Budget min (CHF)</label>
                <input type="range" id="priceMin" min="1000" max="3000" step="100" value="1500" style="width: 120px">
                <span id="priceMinVal">1500</span>
            </div>
            <div class="filter-group">
                <label>Budget max (CHF)</label>
                <input type="range" id="priceMax" min="1500" max="3500" step="100" value="3000" style="width: 120px">
                <span id="priceMaxVal">3000</span>
            </div>
            <div class="filter-group">
                <label>Distanza km</label>
                <input type="number" id="distMax" value="100" min="0" max="1000" style="width: 80px">
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
                <input type="number" id="batteryMin" value="400" min="0" max="1000" style="width: 80px">
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
                <label>Score min</label>
                <input type="number" id="scoreMin" value="60" min="0" max="100" style="width: 80px">
            </div>
            <div class="filter-group">
                <label>&nbsp;</label>
                <label style="flex-direction: row; align-items: center; gap: 5px; font-weight: normal;"><input type="checkbox" id="favOnly" style="width: auto"> ⭐ Solo preferiti</label>
            </div>
            <button onclick="resetFilters()" style="padding: 6px 12px; background: #f44336; color: white; border: none; border-radius: 4px; cursor: pointer; font-size: 13px; font-weight: 600;">Reset</button>
        </div>

        <h2 style="font-size: 18px; margin: 30px 0 15px; padding-bottom: 10px; border-bottom: 2px solid #1976d2;">🏆 Top 10 Deals</h2>
        <div class="top-10">
"""

    for idx, bike in enumerate(top_10, 1):
        score_val = bike["score_total"] or 0
        analysis = _combine_analysis(bike) or "In attesa di valutazione"
        fav_prefix = "⭐ " if bike.get("is_favorite") else ""
        html += f"""            <div class="top-item">
                <div><strong>#{idx}</strong> {fav_prefix}<a href="{bike['url']}" target="_blank">{bike['title']}</a> ({bike['portal']})</div>
                <div class="top-analysis">{analysis}</div>
                <div class="top-meta">Score: {score_val:.1f} | {_format_price(bike)} | {bike['distance_km']:.1f} km</div>
            </div>
"""

    html += """        </div>

        <!-- Analysis Modal -->
        <div id="analysisModal" class="modal">
            <div class="modal-content">
                <span class="modal-close" onclick="closeAnalysis()">&times;</span>
                <h2 id="modalTitle"></h2>
                <div class="modal-body" id="modalBody"></div>
"""

    if interactive:
        html += """                <div class="edit-specs">
                    <h3>✏️ Correggi specifiche (es. hai riconosciuto il motore da una foto)</h3>
                    <div class="edit-fields">
                        <label>Motore <input type="text" id="editMotorBrand" placeholder="es. Bosch"></label>
                        <label>Modello <input type="text" id="editMotorModel" placeholder="es. Performance CX"></label>
                        <label>Coppia Nm <input type="number" id="editMotorTorque"></label>
                        <label>Batteria Wh <input type="number" id="editBattery"></label>
                        <label>Taglia <input type="text" id="editFrame"></label>
                    </div>
                    <button class="btn-save" onclick="saveSpecs()">💾 Salva correzioni</button>
                </div>
                <div class="modal-actions">
                    <button class="btn-reject" onclick="rejectListing()">❌ Scarta</button>
                    <button class="btn-sold" onclick="markSold()">✅ Segna venduta</button>
                    <button class="btn-restore" onclick="restoreListing()">↩️ Ripristina attiva</button>
                </div>
"""

    html += """            </div>
        </div>

        <h2 style="font-size: 18px; margin: 30px 0 15px; padding-bottom: 10px; border-bottom: 2px solid #1976d2;">📋 Tutti gli annunci</h2>
        <table id="table">
            <thead>
                <tr>
                    <th>⭐</th>
                    <th>Score</th>
                    <th>Prezzo</th>
                    <th>Distanza km</th>
                    <th>Motore</th>
                    <th>Batteria Wh</th>
                    <th>Taglia</th>
                    <th>Anno</th>
                    <th>Km</th>
                    <th>Analisi</th>
                    <th>Azioni</th>
                    <th>Status</th>
                    <th>Titolo / Link</th>
                </tr>
            </thead>
            <tbody id="tbody">
"""

    row_templates = []

    for idx, bike in enumerate(listings):
        score_val = bike["score_total"] or 0
        score_class = "high" if score_val >= 80 else "mid" if score_val >= 65 else "low"

        status = bike["status"]
        status_class = (
            "new" if status == "NEW" else
            "price-drop" if status == "PRICE_DROP" else
            "sold" if status == "SOLD" else
            "rejected" if status == "REJECTED" else ""
        )

        motor_text = f"{bike['motor_brand']}" if bike["motor_brand"] else "N/A"
        if bike.get("motor_torque_nm"):
            motor_text += f" {bike['motor_torque_nm']:.0f}Nm"
        if bike.get("motor_verified") == 0:
            motor_text += " ⚠️ da verificare"

        battery_text = f"{bike['battery_capacity_wh']:.0f}Wh" if bike["battery_capacity_wh"] else "N/A"
        frame_text = bike["frame_size"] or "N/A"
        price_text = _format_price(bike)
        anno_text = bike.get("model_year") or "N/A"
        km_text = f"{bike['odometer_km']:.0f}" if bike.get("odometer_km") else "N/A"

        detail_html = _build_detail_html(bike, history_by_id.get(bike["id"], []))
        row_templates.append(f'<template data-listing-id="{_attr(bike["id"])}">{detail_html}</template>')
        is_favorite = bool(bike.get("is_favorite"))

        row_class = "sold" if status == "SOLD" else ""

        if interactive:
            star_cell = f'<button class="star-btn" onclick="toggleFavorite(this)" title="Preferito">{"⭐" if is_favorite else "☆"}</button>'
            actions_cell = (
                '<div class="row-actions">'
                '<button class="btn-reject-sm" onclick="rejectRow(this)" title="Scarta — non mi interessa">❌</button>'
                '<button class="btn-sold-sm" onclick="soldRow(this)" title="Segna come venduta">✅</button>'
                '</div>'
            )
            analysis_btn = '<button class="btn-analysis" onclick="showAnalysis(this)">📋 Dettagli / Correggi</button>'
        else:
            star_cell = "⭐" if is_favorite else ""
            actions_cell = ""
            analysis_btn = '<button class="btn-analysis" onclick="showAnalysis(this)">📋 Analisi</button>'

        html += f"""                <tr class="{row_class}" data-id="{_attr(bike['id'])}" data-favorite="{1 if is_favorite else 0}" data-score="{score_val}" data-price="{bike['price_chf']}" data-distance="{bike['distance_km']}" data-motor="{motor_text}" data-battery="{bike['battery_capacity_wh'] or 0}" data-frame="{frame_text}" data-edit-motor-brand="{_attr(bike.get('motor_brand'))}" data-edit-motor-model="{_attr(bike.get('motor_model'))}" data-edit-motor-torque="{_attr(bike.get('motor_torque_nm'))}" data-edit-battery="{_attr(bike.get('battery_capacity_wh'))}" data-edit-frame="{_attr(bike.get('frame_size'))}">
                    <td>{star_cell}</td>
                    <td><span class="score {score_class}">{score_val:.1f}</span></td>
                    <td>{price_text}</td>
                    <td>{bike['distance_km']:.1f}</td>
                    <td><span class="motor">{motor_text}</span></td>
                    <td>{battery_text}</td>
                    <td>{frame_text}</td>
                    <td>{anno_text}</td>
                    <td>{km_text}</td>
                    <td>{analysis_btn}</td>
                    <td>{actions_cell}</td>
                    <td><span class="status {status_class}">{status}</span></td>
                    <td><a href="{bike['url']}" target="_blank">{bike['title'][:60]}...</a> <br><small>({bike['portal']})</small></td>
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
            const title = row.querySelector('a').textContent;
            document.getElementById('modalTitle').textContent = '📋 ' + title;

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
                document.getElementById('editFrame').value = row.getAttribute('data-edit-frame') || '';
            }

            document.getElementById('analysisModal').classList.add('show');
        }

        function closeAnalysis() {
            document.getElementById('analysisModal').classList.remove('show');
        }

        // Reject / mark sold / restore / spec-correction actions — POST to
        // server.py's API and reload so the page always reflects fresh DB
        // state. Requires the interactive dashboard (python3 server.py);
        // opening index.html directly has no server to answer these.
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

        function saveSpecs() {
            const torque = document.getElementById('editMotorTorque').value;
            const battery = document.getElementById('editBattery').value;
            postAction('specs', {
                motor_brand: document.getElementById('editMotorBrand').value || null,
                motor_model: document.getElementById('editMotorModel').value || null,
                motor_torque_nm: torque !== '' ? parseFloat(torque) : null,
                battery_capacity_wh: battery !== '' ? parseFloat(battery) : null,
                frame_size: document.getElementById('editFrame').value || null
            });
        }

        // Close modal on ESC key
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') closeAnalysis();
        });

        // Close modal on background click
        document.getElementById('analysisModal').addEventListener('click', (e) => {
            if (e.target.id === 'analysisModal') closeAnalysis();
        });

        const priceMinInput = document.getElementById('priceMin');
        const priceMaxInput = document.getElementById('priceMax');
        const priceMinVal = document.getElementById('priceMinVal');
        const priceMaxVal = document.getElementById('priceMaxVal');

        priceMinInput.addEventListener('input', () => {
            priceMinVal.textContent = priceMinInput.value;
            filterTable();
        });
        priceMaxInput.addEventListener('input', () => {
            priceMaxVal.textContent = priceMaxInput.value;
            filterTable();
        });

        document.getElementById('distMax').addEventListener('input', filterTable);
        document.getElementById('motorFilter').addEventListener('change', filterTable);
        document.getElementById('batteryMin').addEventListener('input', filterTable);
        document.getElementById('frameFilter').addEventListener('change', filterTable);
        document.getElementById('scoreMin').addEventListener('input', filterTable);
        document.getElementById('favOnly').addEventListener('change', filterTable);

        function filterTable() {
            const priceMin = parseFloat(priceMinInput.value);
            const priceMax = parseFloat(priceMaxInput.value);
            const distMax = parseFloat(document.getElementById('distMax').value);
            const motorFilter = document.getElementById('motorFilter').value;
            const batteryMin = parseFloat(document.getElementById('batteryMin').value);
            const frameFilter = document.getElementById('frameFilter').value;
            const scoreMin = parseFloat(document.getElementById('scoreMin').value);
            const favOnly = document.getElementById('favOnly').checked;

            const rows = document.querySelectorAll('#tbody tr');
            let visibleCount = 0;

            rows.forEach(row => {
                const price = parseFloat(row.dataset.price);
                const distance = parseFloat(row.dataset.distance);
                const motor = row.dataset.motor;
                const battery = parseFloat(row.dataset.battery);
                const frame = row.dataset.frame;
                const score = parseFloat(row.dataset.score);
                const favorite = row.dataset.favorite === '1';

                let show = true;
                if (price < priceMin || price > priceMax) show = false;
                if (distance > distMax) show = false;
                if (motorFilter && !motor.includes(motorFilter)) show = false;
                if (battery < batteryMin) show = false;
                if (frameFilter && frame !== frameFilter) show = false;
                if (score < scoreMin) show = false;
                if (favOnly && !favorite) show = false;

                row.style.display = show ? '' : 'none';
                if (show) visibleCount++;
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
            document.getElementById('scoreMin').value = 0;
            document.getElementById('favOnly').checked = false;
            filterTable();
        }
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
