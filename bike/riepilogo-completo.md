# Ricerca E-bike Pregassona–Bedano — Riepilogo completo

## Il contesto

- Percorso quotidiano: Via delle Rose, Pregassona → Via Industrie, Bedano (~7 km a tratta, ~14 km A/R)
- Dislivello: discesa iniziale verso Cornaredo/Resega, punto più basso vicino al Cassarate, risalita verso Vezia/Cadempino, tratto pianeggiante lungo il Vedeggio
- Uso: pendolarismo 4-5 giorni/settimana + uscite fuori porta nel weekend (strade bianche/sentieri leggeri, non trail tecnici)
- Budget: **1500-2200 CHF, tutto compreso** (fascia preferita 1500-1800 CHF; 1800-2200 CHF pienamente in budget, "eccezione" nel punteggio)
- Vive a Pregassona (Lugano), lavora a Bedano

## Criteri tecnici (invariati dalla v2.8; Metodologia ora alla v2.9, 22/09/2026 — aggiunte solo regole di processo, non di criteri — vedi Metodologia di ricerca per il dettaglio completo e la cronologia delle decisioni)

- Motore centrale Bosch / Shimano / Brose / Yamaha
- Coppia: **preferita ≥75 Nm, minimo ammesso 65 Nm** — sotto 65 Nm si scarta
- Batteria: **minimo 400 Wh, preferita ≥500 Wh**
- Freni a disco idraulici obbligatori
- Taglia M rigida
- Tipo: **fully preferita**; hardtail accettata solo per un'offerta eccezionale, con condizioni operative concrete (prezzo, motore, batteria, taglia, freni — vedi Metodologia B2)

## Come leggere questo riepilogo

Questo documento è la vista narrativa/ragionata per l'utente: contesto, checklist d'acquisto, questioni pratiche. L'elenco vivo e aggiornato delle candidate (prezzo, giudizio 1-10, parere sincero, stato venduto/rimosso, riclassificazioni) è mantenuto nella **dashboard interattiva** e nel documento "Annunci trovati - log per data" — questo file non duplica più quell'elenco, per evitare che le due fonti vadano fuori sincrono (è già successo una volta: fino al 22/09/2026 questo documento era fermo al 16/09 con criteri e candidate superati).

## Checklist per ispezionare una e-bike usata

1. Numero di telaio corrispondente a scontrino/fattura
2. Stato batteria: km totali sul display, fluidità dell'assistenza durante una prova
3. Telaio: crepe o vernice scrostata vicino alle saldature (no) vs graffi superficiali (ok)
4. Freni: corsa leva decisa, dischi senza rigature profonde
5. Cambio/trasmissione: cambiate fluide, denti corona/pignoni non "a uncino"
6. Sospensioni: assorbono e tornano su morbide, niente perdite d'olio
7. Ruote: nessuna oscillazione laterale, raggi non allentati
8. Prova su strada sempre, prima di comprare
9. Caricabatterie originale incluso, garanzia residua verificata

## Questioni pratiche chiarite

- **Tax-free Italia→Svizzera**: risparmio netto reale ~10-12%, richiede permesso di soggiorno per provare la residenza extra-UE, dichiarazione doganale obbligatoria sopra 150 CHF di franchigia
- **Garanzia Decathlon**: valida in tutti i negozi Decathlon a prescindere dal Paese d'acquisto
- **Normative svizzere pedelec 25km/h**: niente targa/assicurazione/patente, casco non obbligatorio, precedenza da destra, obbligo pista ciclabile se presente
- **Accessori da comprare**: lucchetto robusto, luci, casco, kit foratura, cavalletto, parafanghi, olio catena

## Marchi/modelli scartati e perché

- **Urbanbiker**: problemi di assistenza post-vendita documentati (Trustpilot 2,5-2,7/5)
- **Amflow (DJI)**: prezzo 4200€+, fuori scala per l'uso
- **Zenith X-Active, e-bike cinesi generiche (Engwe/Fiido)**: motore al mozzo, zero assistenza locale
- **Ananda, Bafang, Pixel, Dapu, Tongsheng, Panasonic (motori)**: motori al mozzo o generici, esclusi esplicitamente come marca — non per deduzione
- **Motori proprietari dei produttori di bici** (Specialized, Cannondale/Cabin, Avinox...): trattati come 🟡 "da verificare" finché il testo non conferma un OEM ammesso al loro interno, non scartati automaticamente per il solo nome del produttore — vedi Metodologia A15 e B2

## Calcolo risparmio economico (auto vs ebike)

- Con 4-5 gg/settimana di uso reale: risparmio annuo stimato ~350-365 CHF su carburante
- Payback dell'investimento: ~3,6-4,2 anni a seconda di dove si compra
- Il vero vantaggio economico arriva dal 4° anno in poi

## Stato del progetto al 22/09/2026 (valutazione dopo due audit esterni)

Il progetto è concettualmente solido — fonti, deduplica, cautele di scraping sono buone — ma stava perdendo consistenza operativa: sincronizzazione tra documenti e coerenza di applicazione dei criteri erano il punto debole, più che la strategia di ricerca in sé. Le correzioni sotto (decisioni #19-#22, Metodologia Parte C) hanno chiuso la maggior parte dei problemi segnalati.

**Corretto il 22/09/2026**:

- Le tre incoerenze principali sui criteri rigidi (budget, coppia minima, tipo di telaio) tra Metodologia, istruzioni di progetto e log.
- Riclassificate in dashboard le 12 candidate con coppia 50-64 Nm ora sotto soglia.
- Aggiunta la tabella normativa unica di soglie (coppia/batteria/telaio), eliminando i riferimenti contraddittori sparsi nel documento.
- Formalizzata in condizioni operative concrete (prezzo, motore, batteria, taglia, freni) la regola "hardtail solo per offerta eccezionale" — prima era solo descrittiva.
- Chiarita la policy sui motori proprietari/non riconosciuti (sempre 🟡 "da verificare", mai scarto automatico per il solo nome del produttore).
- Attivate formalmente le regole R-009 (freni dedotti dal modello scritto, con distinzione dato scritto/dedotto) e R-012 (tre livelli di priorità per il 🟡), sia in Metodologia sia nel documento "Apprendimento".
- Implementato in dashboard l'ordinamento predefinito "classificazione, poi punteggio" (un 🟡 con dati mancanti non supera più un 🟢 solo per il punteggio numerico).
- Verificato che il pulsante "Non mi interessa" della dashboard **salva già lo stato in modo persistente** tramite la pubblicazione live su claude.ai — non era un problema reale sulla dashboard live, solo sulla copia esportata in locale (già documentato lì).
- Assegnato automaticamente il livello di priorità R-012 (🟡-A/B/C) a tutte le 118 candidate 🟡 in dashboard, contando i dati decisivi mancanti nel testo — è una classificazione euristica, segnalata come tale in dashboard, non una revisione manuale annuncio per annuncio.
- Aggiunte in Metodologia le regole A16 ("conoscenza tecnica: verificare, non inventare" — su un dubbio tecnico generale, cercare online invece di rispondere a memoria) e il rafforzamento di A14 ("onestà anche scomoda" — i pareri restano sinceri anche quando negativi).
- **Moustache Samedi 29 (Cadenazzo) confermata da fonte diretta**: l'utente ha fornito il link dell'annuncio reale su tutti.ch; tutti i dati tecnici riferiti in precedenza (Bosch CX 85 Nm, 625 Wh, taglia M, freni idraulici Shimano XT) sono risultati scritti testualmente nell'annuncio. Riclassificata da 🟡 a 🟢 in dashboard, rating 9.2 — una delle candidate più forti dell'intera ricerca. Unico limite reale: ritiro solo in loco a Cadenazzo (no spedizione); il prezzo scritto è 2'200 CHF, la trattativa verso 2'000 CHF resta riferita dall'utente, non confermata per iscritto sull'annuncio.

**Ancora da fare, in ordine di priorità** (vedi Metodologia Parte C "Ancora aperte" per il dettaglio):

1. Rivedere manualmente i tag 🟡-A/B/C assegnati euristicamente il 22/09/2026 (l'algoritmo può sbagliare su frasi ambigue) — il campo `priority` ora esiste in dashboard, ma resta un'ipotesi automatica da confermare candidata per candidata.
2. Valutare una fonte dati unica strutturata (es. `candidates.json`) da cui derivare dashboard, log e riepilogo, per evitare futuri disallineamenti.

## Prossimi passi

- Organizzare il ritiro di persona a Cadenazzo per la Moustache Samedi 29, se l'utente vuole procedere, e verificare col venditore se la trattativa verso 2'000 CHF è ancora valida
- Valutare le candidate 🟢 con giudizio più alto nella dashboard (verificare disponibilità aggiornata, alcune risultano vendute)
- Decidere se aspettare la primavera o procedere ora
- Collegare l'email a Claude per leggere le notifiche delle ricerche salvate automaticamente

---

**Nota (22/09/2026)**: questo documento era rimasto fermo al 16/09/2026, con criteri e un elenco di candidate ormai superati dalla dashboard e dal log. Aggiornato più volte lo stesso giorno per riportarlo in sincrono con Metodologia v2.9; l'elenco dettagliato delle candidate non viene più mantenuto qui (vedi "dashboard-e-mtb-tracker" e "Annunci trovati - log per data").
