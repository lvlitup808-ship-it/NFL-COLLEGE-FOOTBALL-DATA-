import pytest
from pydantic import ValidationError
from app.scenario_store import Scenario

def valid():
    return {"version":"fieldmind-synthetic-v1","synthetic":True,"name":"Test","players":[
        {"id":f"p{i}","name":f"Player {i}","x":10,"y":20,"routes":[{"x":30,"y":40}]}
        for i in range(1,15)]}

def test_roundtrip():
    scenario=Scenario.model_validate(valid())
    assert Scenario.model_validate_json(scenario.model_dump_json())==scenario

@pytest.mark.parametrize("change",[
    lambda d: d.update(version="fieldmind-synthetic-v2"),
    lambda d: d.update(synthetic=False),
    lambda d: d["players"][0].update(x=101),
    lambda d: d["players"][0].update(routes=[{"x":float("nan"),"y":10}]),
    lambda d: d["players"][0].update(id="p2"),
    lambda d: d["players"][0].update(routes=[{"x":0,"y":0}]*201),
])
def test_reject_invalid(change):
    data=valid();change(data)
    with pytest.raises(ValidationError):
        Scenario.model_validate(data)
