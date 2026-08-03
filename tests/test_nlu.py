"""
Unit tests for simple NLU rules: list_all, class detection and count detection.

These tests are lightweight and do not require Ollama or Chroma.
"""

from modules.rag.nlu import detect_classe_mention, is_list_all_intent, is_count_intent


def test_is_list_all_intent_examples():
    assert is_list_all_intent("Quelles sont toutes les matières du programme 4 ERP-BI ?")
    assert is_list_all_intent("Donne la liste des matières de 4 ERP-BI")
    assert is_list_all_intent("Liste les matieres pour 4 ERP-BI")
    assert is_list_all_intent("Quels sont les paniers que je dois valider pour 3B ?")
    assert is_list_all_intent("C'est quoi les matières que j'étudie dans la classe 4 BI?")


def test_detect_classe_mention_prefers_exact_3b():
    assert detect_classe_mention("Je suis étudiant en 3B à ESPRIT") == "3B"


def test_detect_classe_mention_handles_4_bi():
    assert detect_classe_mention("C'est quoi les matières que j'étudie dans la classe 4 BI?") == "4 ERP-BI"


def test_is_count_intent_examples():
    assert is_count_intent("Combien de matières y a-t-il dans le programme 4 ERP-BI ?")
    assert is_count_intent("Quel est le nombre de modules en 4 ERP-BI ?")
    # count intent should not be true for unrelated questions
    assert not is_count_intent("Quelle est la date de rentrée ?")
