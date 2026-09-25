#!/usr/bin/env python3
"""Generate static HTML dashboard from DB listings."""

import sys
from pathlib import Path
from datetime import datetime

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from db.database import Database
import yaml


def generate_dashboard(db_path: str, output_path: str = "index.html"):
    """Generate HTML dashboard from DB."""
    db = Database(db_path)

    # Fetch all active/price_drop listings with scores + specs
    cursor = db.conn.cursor()
    cursor.execute("""
    SELECT
        l.id, l.portal, l.title, l.price_chf, l.distance_km, l.url,
        l.last_seen_at, l.status, l.user_analysis,
        s.motor_brand, s.motor_torque_nm, s.motor_verified, s.battery_capacity_wh, s.frame_size,
        s.travel_front_mm, s.brakes_tier, s.has_red_flag,
        sc.score_total, sc.score_price_value, sc.score_component_quality,
        sc.score_fit_geometry
    FROM listings l
    LEFT JOIN specifications s ON l.id = s.listing_id
    LEFT JOIN scores sc ON l.id = sc.listing_id
    WHERE l.status IN ('ACTIVE', 'NEW', 'PRICE_DROP') AND l.rejection_reason IS NULL
    ORDER BY COALESCE(sc.score_total, 0) DESC, l.price_chf ASC
    """)

    listings = [dict(row) for row in cursor.fetchall()]
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
        .modal-body {{ white-space: pre-wrap; font-size: 14px; line-height: 1.6; }}

        .btn-analysis {{ padding: 4px 8px; background: #1976d2; color: white; border: none; border-radius: 3px; cursor: pointer; font-size: 11px; font-weight: 600; }}
        .btn-analysis:hover {{ background: #1565c0; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>🚲 E-Bike Hunter Dashboard</h1>
        <div class="meta">Aggiornato: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | {len(listings)} annunci trovati</div>
        <div class="meta">⚠️ Portali bloccati (controllo manuale): <a href="https://www.decathlon.ch/search?from=0&size=40" target="_blank">Decathlon.ch</a> (Cloudflare)</div>

        <div class="filters">
            <div class="filter-group">
                <label>Prezzo CHF</label>
                <input type="range" id="priceMin" min="1000" max="3000" step="100" value="1500" style="width: 120px">
                <span id="priceMinVal">1500</span>
            </div>
            <div class="filter-group">
                <label>Prezzo max</label>
                <input type="range" id="priceMax" min="1500" max="3500" step="100" value="3000" style="width: 120px">
                <span id="priceMaxVal">3000</span>
            </div>
            <div class="filter-group">
                <label>Distanza km</label>
                <input type="number" id="distMax" value="100" min="0" max="500" style="width: 80px">
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
            <button onclick="resetFilters()" style="padding: 6px 12px; background: #f44336; color: white; border: none; border-radius: 4px; cursor: pointer; font-size: 13px; font-weight: 600;">Reset</button>
        </div>

        <h2 style="font-size: 18px; margin: 30px 0 15px; padding-bottom: 10px; border-bottom: 2px solid #1976d2;">🏆 Top 10 Deals</h2>
        <div class="top-10">
"""

    for idx, bike in enumerate(top_10, 1):
        score_val = bike["score_total"] or 0
        analysis = bike["user_analysis"] or "In attesa di valutazione"
        html += f"""            <div class="top-item">
                <div><strong>#{idx}</strong> <a href="{bike['url']}" target="_blank">{bike['title']}</a> ({bike['portal']})</div>
                <div class="top-analysis">{analysis}</div>
                <div class="top-meta">Score: {score_val:.1f} | {bike['price_chf']:.0f} CHF | {bike['distance_km']:.1f} km</div>
            </div>
"""

    html += """        </div>

        <!-- Analysis Modal -->
        <div id="analysisModal" class="modal">
            <div class="modal-content">
                <span class="modal-close" onclick="closeAnalysis()">&times;</span>
                <h2 id="modalTitle"></h2>
                <div class="modal-body" id="modalBody"></div>
            </div>
        </div>

        <h2 style="font-size: 18px; margin: 30px 0 15px; padding-bottom: 10px; border-bottom: 2px solid #1976d2;">📋 Tutti gli annunci</h2>
        <table id="table">
            <thead>
                <tr>
                    <th>Score</th>
                    <th>Prezzo CHF</th>
                    <th>Distanza km</th>
                    <th>Motore</th>
                    <th>Batteria Wh</th>
                    <th>Taglia</th>
                    <th>Analisi</th>
                    <th>Status</th>
                    <th>Titolo / Link</th>
                </tr>
            </thead>
            <tbody id="tbody">
"""

    for idx, bike in enumerate(listings):
        score_val = bike["score_total"] or 0
        score_class = "high" if score_val >= 80 else "mid" if score_val >= 65 else "low"

        status = bike["status"]
        status_class = "new" if status == "NEW" else "price-drop" if status == "PRICE_DROP" else "sold" if status == "SOLD" else ""

        motor_text = f"{bike['motor_brand']}" if bike["motor_brand"] else "N/A"
        if bike.get("motor_torque_nm"):
            motor_text += f" {bike['motor_torque_nm']:.0f}Nm"
        if bike.get("motor_verified") == 0:
            motor_text += " ⚠️ da verificare"

        battery_text = f"{bike['battery_capacity_wh']:.0f}Wh" if bike["battery_capacity_wh"] else "N/A"
        frame_text = bike["frame_size"] or "N/A"

        analysis = bike["user_analysis"] or ""

        row_class = "sold" if status == "SOLD" else ""
        # Escape analysis for JS
        analysis_escaped = analysis.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")

        html += f"""                <tr class="{row_class}" data-score="{score_val}" data-price="{bike['price_chf']}" data-distance="{bike['distance_km']}" data-motor="{motor_text}" data-battery="{bike['battery_capacity_wh'] or 0}" data-frame="{frame_text}" data-analysis="{analysis_escaped}">
                    <td><span class="score {score_class}">{score_val:.1f}</span></td>
                    <td>{bike['price_chf']:.0f}</td>
                    <td>{bike['distance_km']:.1f}</td>
                    <td><span class="motor">{motor_text}</span></td>
                    <td>{battery_text}</td>
                    <td>{frame_text}</td>
                    <td><button class="btn-analysis" onclick="showAnalysis(this)">📋 Analisi</button></td>
                    <td><span class="status {status_class}">{status}</span></td>
                    <td><a href="{bike['url']}" target="_blank">{bike['title'][:60]}...</a> <br><small>({bike['portal']})</small></td>
                </tr>
"""

    html += """            </tbody>
        </table>
    </div>

    <script>
        // Modal functions
        function showAnalysis(button) {
            const row = button.closest('tr');
            const analysis = row.getAttribute('data-analysis');
            const title = row.querySelector('a').textContent;
            document.getElementById('modalTitle').textContent = '📋 ' + title;
            document.getElementById('modalBody').textContent = analysis;
            document.getElementById('analysisModal').classList.add('show');
        }

        function closeAnalysis() {
            document.getElementById('analysisModal').classList.remove('show');
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

        function filterTable() {
            const priceMin = parseFloat(priceMinInput.value);
            const priceMax = parseFloat(priceMaxInput.value);
            const distMax = parseFloat(document.getElementById('distMax').value);
            const motorFilter = document.getElementById('motorFilter').value;
            const batteryMin = parseFloat(document.getElementById('batteryMin').value);
            const frameFilter = document.getElementById('frameFilter').value;
            const scoreMin = parseFloat(document.getElementById('scoreMin').value);

            const rows = document.querySelectorAll('#tbody tr');
            let visibleCount = 0;

            rows.forEach(row => {
                const price = parseFloat(row.dataset.price);
                const distance = parseFloat(row.dataset.distance);
                const motor = row.dataset.motor;
                const battery = parseFloat(row.dataset.battery);
                const frame = row.dataset.frame;
                const score = parseFloat(row.dataset.score);

                let show = true;
                if (price < priceMin || price > priceMax) show = false;
                if (distance > distMax) show = false;
                if (motorFilter && !motor.includes(motorFilter)) show = false;
                if (battery < batteryMin) show = false;
                if (frameFilter && frame !== frameFilter) show = false;
                if (score < scoreMin) show = false;

                row.style.display = show ? '' : 'none';
                if (show) visibleCount++;
            });

            const tbody = document.getElementById('tbody');
            let info = tbody.querySelector('.filter-info');
            if (info) info.remove();

            if (visibleCount === 0) {
                const noResult = document.createElement('tr');
                noResult.className = 'filter-info';
                noResult.innerHTML = '<td colspan="9" style="text-align: center; padding: 20px; color: #999;">Nessun risultato con questi filtri</td>';
                tbody.appendChild(noResult);
            }
        }

        function resetFilters() {
            priceMinInput.value = 1500;
            priceMaxInput.value = 3000;
            priceMinVal.textContent = 1500;
            priceMaxVal.textContent = 3000;
            document.getElementById('distMax').value = 100;
            document.getElementById('motorFilter').value = '';
            document.getElementById('batteryMin').value = 400;
            document.getElementById('frameFilter').value = '';
            document.getElementById('scoreMin').value = 60;
            filterTable();
        }
    </script>
</body>
</html>
"""

    # Write HTML
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"✓ Dashboard generated: {output_path} ({len(listings)} listings, top 10 deals)")


if __name__ == "__main__":
    import os
    config_path = Path(__file__).parent.parent / "config" / "config.yaml"
    with open(config_path) as f:
        config = yaml.safe_load(f)

    db_path = config["app"]["db_path"]
    output = Path(__file__).parent.parent / "index.html"

    generate_dashboard(db_path, str(output))
