import json
import shutil

import pytest

from conftest import ROOT
from deallens.config import ConfigError, load_config


def test_repo_config_loads_with_versions(config):
    assert [p.model_key for p in config.products] == ["X1504VAP-BQ224WS", "X1504MA-BQ832WS", "X1504VA-NJ2324WS"]
    assert [(p.ref, p.status) for p in config.plans] == [("vivobook15-broad@1", "retired"),
                                                         ("vivobook15-broad@2", "provisional")]
    assert [p.ref for p in config.active_plans] == ["vivobook15-broad@2"]
    assert config.versions == {"products": "products-2", "plans": "plans-2", "sellers": "seller-map-1",
                               "rules": "rules-1", "coverage": "coverage-1", "collector": "collector-3"}
    assert config.collector.min_remaining == 60


def _broken(tmp_path, file, mutate):
    d = tmp_path / "config"
    shutil.copytree(ROOT / "config", d)
    doc = json.loads((d / file).read_text(encoding="utf-8"))
    mutate(doc)
    (d / file).write_text(json.dumps(doc), encoding="utf-8")
    return d


def test_alias_shared_by_two_products_is_rejected(tmp_path):
    d = _broken(tmp_path, "products.json", lambda doc: doc["products"][1]["aliases"].append("X1504VAP-BQ224WS"))
    with pytest.raises(ConfigError, match="alias"):
        load_config(d)


def test_active_plan_serving_unknown_product_is_rejected(tmp_path):
    d = _broken(tmp_path, "query_plans.json", lambda doc: doc["plans"][1]["serves"].append("nope"))
    with pytest.raises(ConfigError, match="nope"):
        load_config(d)


def test_retired_plan_may_name_a_retired_product(config):
    assert "asus-x1504vap-bq541ws" in config.plan("vivobook15-broad@1").serves          # provenance kept
    assert "asus-x1504vap-bq541ws" not in [p.product_key for p in config.products]


def test_overlapping_related_groups_are_rejected(tmp_path):
    def mutate(doc):
        doc["related_groups"][1]["storefronts"].append("asus.com")
    with pytest.raises(ConfigError, match="asus.com"):
        load_config(_broken(tmp_path, "sellers.json", mutate))
