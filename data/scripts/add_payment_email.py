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

OUTPUT_PATH = r"C:\Users\zizou\Desktop\stage_ia_recepsionist\data\processed\site_esprit.json"

ANNEE_UNIVERSITAIRE = "2024-2025"
SOURCE = f"Email de paiement/réinscription {ANNEE_UNIVERSITAIRE}"

RECORDS = [
    {
        "id": f"paiements_{ANNEE_UNIVERSITAIRE}_reinscription",
        "categorie": "Paiements",
        "titre": f"Date limite de réinscription {ANNEE_UNIVERSITAIRE}",
        "contenu": (
            f"La réinscription pour l'année universitaire {ANNEE_UNIVERSITAIRE} est possible dès "
            f"réception du mail. Le dernier délai pour se réinscrire est fixé au 31/08/2024."
        ),
    },
    {
        "id": f"paiements_{ANNEE_UNIVERSITAIRE}_montant_total",
        "categorie": "Paiements",
        "titre": f"Montant des frais de scolarité {ANNEE_UNIVERSITAIRE}",
        "contenu": (
            f"Pour l'année universitaire {ANNEE_UNIVERSITAIRE}, les frais de scolarité s'élèvent à "
            f"8200,0 dinars par an, payables en deux tranches."
        ),
    },
    {
        "id": f"paiements_{ANNEE_UNIVERSITAIRE}_tranche1",
        "categorie": "Paiements",
        "titre": f"1ère tranche des frais de scolarité {ANNEE_UNIVERSITAIRE}",
        "contenu": (
            "La 1ère tranche des frais de scolarité est de 4050 DT, payable avant le 31/08/2024, "
            "exigée dès l'inscription."
        ),
    },
    {
        "id": f"paiements_{ANNEE_UNIVERSITAIRE}_tranche2",
        "categorie": "Paiements",
        "titre": f"2ème tranche des frais de scolarité {ANNEE_UNIVERSITAIRE}",
        "contenu": "La 2ème tranche des frais de scolarité est de 4150,0 DT, payable avant le 15 janvier 2025.",
    },
    {
        "id": f"paiements_{ANNEE_UNIVERSITAIRE}_moyens_paiement",
        "categorie": "Paiements",
        "titre": "Moyens de paiement des frais de scolarité",
        "contenu": (
            "Les frais de scolarité peuvent être réglés de trois façons : en ligne par carte bancaire "
            "via le lien https://esprit-tn.com/ESPOnline/Online/Login.aspx ; par versement d'espèces "
            "dans n'importe quelle agence BIAT en indiquant le nom, l'identifiant étudiant et le "
            "numéro de compte d'ESPRIT (51 10 98009 6) sur l'ordre de versement ; ou par chèque "
            "bancaire ou postal libellé au nom d'ESPRIT, à déposer auprès du service financier de l'école."
        ),
    },
    {
        "id": f"paiements_{ANNEE_UNIVERSITAIRE}_reduction_merite",
        "categorie": "Paiements",
        "titre": "Réductions pour mérite académique",
        "contenu": (
            "Des réductions sont accordées annuellement aux étudiants les plus méritants : 30% de "
            "réduction pour les élèves ayant une moyenne supérieure à 15/20 et classés premiers de "
            "leur classe ; 15% de réduction pour les élèves classés premiers de leur classe ayant "
            "une moyenne comprise entre 13/20 et 15/20."
        ),
    },
    {
        "id": f"paiements_{ANNEE_UNIVERSITAIRE}_reduction_fratrie",
        "categorie": "Paiements",
        "titre": "Réductions pour fratrie",
        "contenu": (
            "Des réductions sont accordées annuellement aux étudiants issus d'une même famille "
            "(frères et/ou sœurs) : 25% pour le deuxième enfant, 30% pour le troisième enfant. Les "
            "réductions sont calculées sur les frais de scolarité les plus élevés, sur présentation "
            "à la direction financière d'une demande jointe des copies des cartes d'identité de la fratrie."
        ),
    },
    {
        "id": f"paiements_{ANNEE_UNIVERSITAIRE}_financement_fondation",
        "categorie": "Paiements",
        "titre": "Financement via la Fondation ESPRIT",
        "contenu": (
            "Il existe une possibilité de financement par l'intermédiaire du dispositif d'octroi de "
            "prêts régi par la Fondation ESPRIT (www.esprit-fondation.tn)."
        ),
    },
    {
        "id": f"paiements_{ANNEE_UNIVERSITAIRE}_financement_bancaire",
        "categorie": "Paiements",
 "titre": "Financement par prêt bancaire",
        "contenu": (
            "Il existe une possibilité de financement moyennant un prêt bancaire, octroyé en "
            "application des conventions conclues avec les banques partenaires : Amen Banque, "
            "Zitouna et l'UBCI."
        ),
    },
    {
        "id": f"paiements_{ANNEE_UNIVERSITAIRE}_facilite_mensualites",
        "categorie": "Paiements",
        "titre": "Paiement en plusieurs mensualités",
        "contenu": "Une facilité de paiement pouvant aller jusqu'à 36 mensualités est proposée aux étudiants.",
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
