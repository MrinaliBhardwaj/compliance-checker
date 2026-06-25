"""Unit tests — seed loader (M2 acceptance, pure parse layer; no DB)."""
import copy

import pytest

from app.seed.library_loader import (
    SeedValidationError,
    library_stats,
    load_library,
    validate_library,
)


def test_counts(library):
    stats = library_stats(library)
    assert stats["laws"] == 29
    assert stats["templates"] == 106
    assert stats["due_rule_types"] == 30


def test_all_templates_draft_unverified(library):
    """The DRAFT_UNVERIFIED content gate is real data, not a doc footnote."""
    stats = library_stats(library)
    assert stats["by_verification"] == {"DRAFT_UNVERIFIED": 106}


def test_load_is_pure_and_repeatable():
    a = load_library()
    b = load_library()
    assert library_stats(a) == library_stats(b)


def test_validation_catches_dangling_law_id(library):
    bad = copy.deepcopy(library)
    bad["obligation_templates"][0]["law_id"] = "law_does_not_exist"
    with pytest.raises(SeedValidationError, match="unknown law_id"):
        validate_library(bad)


def test_validation_catches_duplicate_template_id(library):
    bad = copy.deepcopy(library)
    bad["obligation_templates"].append(copy.deepcopy(bad["obligation_templates"][0]))
    with pytest.raises(SeedValidationError, match="duplicate template id"):
        validate_library(bad)


def test_validation_catches_missing_keys(library):
    bad = copy.deepcopy(library)
    del bad["obligation_templates"][0]["due_rule"]
    with pytest.raises(SeedValidationError, match="missing keys"):
        validate_library(bad)
