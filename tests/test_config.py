from or_extractor.config import (
    DEFAULT_WANTED_COLUMNS,
    normalize_wanted_columns,
    normalize_zeendoc_base_url,
    normalize_zeendoc_binder_id,
)


def test_normalize_base_url_adds_api_v4():
    assert (
        normalize_zeendoc_base_url("https://armoires.zeendoc.com/armoire")
        == "https://armoires.zeendoc.com/armoire/api/v4"
    )


def test_normalize_binder_id_accepts_numeric_shortcut():
    assert normalize_zeendoc_binder_id("1") == "coll_1"
    assert normalize_zeendoc_binder_id("coll_24") == "coll_24"


def test_normalize_wanted_columns_maps_labels_and_expands_minimal_columns():
    assert normalize_wanted_columns("Res_Id,Upload_Id") == DEFAULT_WANTED_COLUMNS
    assert (
        normalize_wanted_columns("Res_Id,Informations Générales|Client")
        == "Res_Id,custom_t2"
    )
