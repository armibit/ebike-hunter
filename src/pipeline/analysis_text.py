"""Deterministic, human-readable verdict text for a listing (Italian).

Kept deliberately narrower than the full spec set: the detail card's spec
grid already shows motor/battery/frame/suspension/brakes with a
verified/unverified badge, so restating each one here as a bullet would
just be duplicate reading — this covers only what the grid can't (a
qualitative condition read, distance framing, price framing, red flags)
plus the headline verdict and recommendation.
"""
from typing import Any, Dict

# Portals that only list brand-new stock, and the one that only sells
# factory-refurbished bikes. Everything else is a private-seller marketplace.
NEW_PORTALS = {
    "buybestgear", "ebikelab", "ebikestorebrescia", "ecycles_shop",
    "godspeed", "ridewill", "zbike", "tcs_velocorner",
}
REFURBISHED_PORTALS = {"upway"}


def condition_label(portal: str) -> str:
    """New / refurbished / used, inferred from the portal the listing came from
    (no per-listing condition field exists in the DB)."""
    portal = (portal or "").lower()
    if portal in NEW_PORTALS:
        return "Nuovo"
    if portal in REFURBISHED_PORTALS:
        return "Ricondizionato"
    return "Usato"


def generate_user_analysis(score: float, specs: Dict[str, Any], listing_data: Dict[str, Any]) -> str:
    odometer = specs.get("odometer_km")
    distance = listing_data.get("distance_km", 0)
    price = listing_data.get("price_chf", 0)
    red_flags = specs.get("red_flag_details", [])

    lines = []

    if score >= 85:
        verdict = "🟢 FORTEMENTE CONSIGLIATA - Prima scelta da vedere"
    elif score >= 75:
        verdict = "🟡 DA CONSIDERARE - Buon equilibrio tra le specifiche"
    elif score >= 65:
        verdict = "🟠 ACCETTABILE - Rispetta i requisiti minimi"
    else:
        verdict = "🔴 PRIORITÀ BASSA - Non è un match ideale"
    lines.append(f"**{verdict}**\n")

    if odometer:
        if odometer < 500:
            cond_note = "Chilometraggio molto basso ✓✓"
        elif odometer < 2000:
            cond_note = "Chilometraggio basso ✓"
        elif odometer < 5000:
            cond_note = "Utilizzo normale"
        else:
            cond_note = "Chilometraggio alto — verifica le condizioni"
        lines.append(f"• Condizione: {odometer:.0f} km — {cond_note}")

    if distance < 15:
        dist_note = f"Molto vicina ({distance:.1f}km) ✓✓ — Facile da visitare"
    elif distance < 30:
        dist_note = f"Nelle vicinanze ({distance:.1f}km) ✓ — Raggiungibile in treno"
    elif distance < 60:
        dist_note = f"Distanza media ({distance:.1f}km) — Organizza la trasferta"
    else:
        dist_note = f"Lontana ({distance:.1f}km) — Vale la pena solo con specifiche molto buone"
    lines.append(f"• Posizione: {dist_note}")

    target_price = 2200
    if price < 1800:
        price_note = f"Sotto il target ({price:.0f} CHF) ✓✓ — Ottimo affare"
    elif price < target_price:
        price_note = f"Nel budget ({price:.0f} CHF, target {target_price}) ✓"
    else:
        price_note = f"Sopra il target ({price:.0f} CHF, target {target_price}) — Prova a negoziare"
    lines.append(f"• Prezzo: {price_note}")

    if red_flags:
        flag_str = ", ".join(red_flags[:3])
        lines.append(f"\n⚠️  Segnalazioni: {flag_str}")

    lines.append(f"\n**Raccomandazione**: Punteggio {score:.0f}/100. " +
                ("Vale la pena andare a vederla di persona — alta probabilità di match." if score >= 80 else
                 "Buona opzione, vale la pena approfondire." if score >= 70 else
                 "Accettabile ma non ideale. Confronta prima con altre opzioni."))

    return "\n".join(lines)
