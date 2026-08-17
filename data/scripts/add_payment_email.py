"""
Ajoute les informations clés d'un mail annuel de paiement/réinscription
à la base de connaissances, dans une catégorie "Paiements" dédiée.

Contrairement aux scripts précédents, ce script ne scrape rien : le texte
source est un mail reçu par email, donc les fiches sont écrites à la main
ci-dessous, découpées par information précise pour une meilleure recherche.

A chaque nouvelle année universitaire, remplace le contenu de RECORDS avec
les infos du nouveau mail, et change ANNEE_UNIVERSITAIRE.

Lancement :
    python add_payment_email.py
"""

import os
import json

OUTPUT_PATH = r"d:\stage_ia_recepsionist\data\processed\site_esprit.json"

ANNEE_UNIVERSITAIRE = "2026-2027"
ANNEE_SLASH = "2026/2027"
SOURCE = f"Email de paiement/réinscription {ANNEE_UNIVERSITAIRE} (Direction ESPRIT)"

RECORDS = [
    {
        "id": f"paiements_{ANNEE_UNIVERSITAIRE}_montant_total",
        "categorie": "Paiements",
        "titre": f"Quels sont les frais d'inscription (frais de scolarité) pour l'année {ANNEE_SLASH} ?",
        "contenu": (
            f"Les frais d'inscription (aussi appelés frais de scolarité) pour les cours du jour "
            f"(étudiants tunisiens) pour l'année {ANNEE_SLASH} s'élèvent au total à 8 500 TND TTC "
            f"(TVA 7% incluse), payables en deux tranches : 4050 TND avant le 31/08/2026 (exigée à "
            f"l'inscription), 4450 TND avant le 15 janvier 2027. Le dernier délai pour se réinscrire "
            f"pour l'année {ANNEE_SLASH} est fixé au 31/08/2026."
        ),
    },
]

for record in RECORDS:
    record["source"] = SOURCE


def load_existing(path: str) -> list[dict]:
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def merge_records(existing: list[dict], new_records: list[dict]) -> list[dict]:
    existing_ids = {r["id"] for r in existing}
    added = 0
    for record in new_records:
        if record["id"] in existing_ids:
            continue
        existing.append(record)
        existing_ids.add(record["id"])
        added += 1
    print(f"{added} nouvelles fiches ajoutées (doublons ignorés automatiquement).")
    return existing


if __name__ == "__main__":
    existing = load_existing(OUTPUT_PATH)
    merged = merge_records(existing, RECORDS)

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)

    print(f"Total dans la base de connaissances : {len(merged)} fiches -> {OUTPUT_PATH}")
