import asyncio
from app.connectors.planning import planning_history_result
from app.source_status import SourceState


def test_planning_history_without_verified_uprn_is_incomplete():
    result=asyncio.run(planning_history_result(53.0,-1.0,None))
    assert result.state == SourceState.incomplete
    assert result.records == []
