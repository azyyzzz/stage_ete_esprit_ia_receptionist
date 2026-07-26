"""
Unit tests for simple NLU rules: list_all and count detection.

These tests are lightweight and do not require Ollama or Chroma.
"""

from modules.rag.nlu import is_list_all_intent, is_count_intent


def test_is_list_all_intent_examples():
    assert is_list_all_intent("Quelles sont toutes les matières du programme 4 ERP-BI ?")
    assert is_list_all_intent("Donne la liste des matières de 4 ERP-BI")
    assert is_list_all_intent("Liste les matieres pour 4 ERP-BI")


def test_is_count_intent_examples():
    assert is_count_intent("Combien de matières y a-t-il dans le programme 4 ERP-BI ?")
    assert is_count_intent("Quel est le nombre de modules en 4 ERP-BI ?")
    # count intent should not be true for unrelated questions
    assert not is_count_intent("Quelle est la date de rentrée ?")
