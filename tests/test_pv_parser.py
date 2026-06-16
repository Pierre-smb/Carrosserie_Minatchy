from decimal import Decimal

from or_extractor.pv_parser import extract_text_fields, parse_expert_report_pages


def test_parse_liste_des_pieces_until_total_across_pages():
    pages = [
        """
        Rapport expertise
        Liste des pieces
        Qte Libelle Reference Operation Montant HT
        1 Pare-chocs avant REF PC-AV-001 remplacement 250,00
        2 Agrafe fixation REF AGR-22 pose 12,50
        """,
        """
        Suite du chiffrage
        1 Aile avant gauche REF AILE-G peinture 180,00
        TOTAL HT 442,50
        Observations
        """,
    ]

    extracted = parse_expert_report_pages(pages)

    assert extracted.kind == "pieces"
    assert len(extracted.lines) == 3
    assert extracted.lines[0].quantity == Decimal("1")
    assert extracted.lines[0].reference == "PC-AV-001"
    assert extracted.lines[0].amount_ht == Decimal("250.00")
    assert extracted.lines[2].page == 2
    assert extracted.total_ht == Decimal("442.50")


def test_parse_liste_des_fournitures_with_continuation_line():
    pages = [
        """
        Liste des fournitures
        Qte Libelle Montant HT
        1 Kit peinture complet 85,40
        teinte constructeur specifique
        TOTAL 85,40
        """
    ]

    extracted = parse_expert_report_pages(pages)

    assert extracted.kind == "fournitures"
    assert len(extracted.lines) == 1
    assert extracted.lines[0].label == "Kit peinture complet teinte constructeur specifique"
    assert extracted.lines[0].amount_ht == Decimal("85.40")


def test_normalizes_operation_codes_to_business_labels():
    pages = [
        """
        Liste des fournitures
        PORTE AV G 1098,60 E P
        AILE AV G R P
        RETROVISEUR EXT G 284,55 EP
        TOTAL FOURNITURES H.T. .... 1383,15
        """
    ]

    extracted = parse_expert_report_pages(pages)

    assert extracted.lines[0].operation == "Echange + Peinture"
    assert extracted.lines[1].operation == "Reparation + Peinture"
    assert extracted.lines[2].operation == "Echange + Peinture"


def test_parse_piece_without_reference_keeps_operation_and_amount_in_right_columns():
    pages = [
        """
        Liste des pieces
        !1!PROTECTEUR DE GACHE D DE CAPOT-MOTEU!E!8,50!
        TOTAL PIECES 8,50
        """
    ]

    extracted = parse_expert_report_pages(pages)

    assert extracted.lines[0].quantity == Decimal("1")
    assert extracted.lines[0].label == "PROTECTEUR DE GACHE D DE CAPOT-MOTEU"
    assert extracted.lines[0].reference is None
    assert extracted.lines[0].operation == "Echange"
    assert extracted.lines[0].amount_ht == Decimal("8.50")


def test_parse_piece_without_reference_accepts_other_operation_codes():
    pages = [
        """
        Liste des pieces
        !1!PROJECTEURS G, D!G!8,50!
        TOTAL PIECES 8,50
        """
    ]

    extracted = parse_expert_report_pages(pages)

    assert extracted.lines[0].label == "PROJECTEURS G, D"
    assert extracted.lines[0].reference is None
    assert extracted.lines[0].operation == "Reglage"
    assert extracted.lines[0].amount_ht == Decimal("8.50")


def test_extract_text_fields_from_ocr_sections():
    text = """
    CONSTATES CENTRAL/LATERAL GAUCHE ! 29 RUE MIKA BARRAGE
    -LISTE DES FOURNITURES !Postes Temps Taux Hor. Total HT
    Libelle Prix H.T Ope
    PORTE AV G 1098,60 E P
    TOTAL FOURNITURES H.T. .... 1098,60 E
    -OBSERVATIONS- !
    REPONSE EAD !
    Accord sur Fournitures : OUI !TOTAL HT : 2087,99 TVA: 177,49
    Nous communiquer la date des travaux par !-----------------------------------
    retour, svp. !
    Ce document ne peut etre considere comme !
    """
    extracted = parse_expert_report_pages([text])

    fields = extract_text_fields(text, extracted)

    assert fields.work_designation == "CONSTATES CENTRAL/LATERAL GAUCHE"
    assert fields.observations == (
        "REPONSE EAD\n"
        "Accord sur Fournitures : OUI\n"
        "Nous communiquer la date des travaux par\n"
        "retour, svp."
    )
    assert fields.indexed_items == ["PORTE AV G"]
