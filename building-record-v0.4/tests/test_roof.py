from app.models import Fact, Source, EvidenceStatus
from app.roof import build_roof

def test_roof_preserves_source_and_unknowns():
    src=Source(provider="Test",dataset="buildings")
    roof=build_roof("br_test",[Fact(attribute="roof shape",value="gable",
                                    status=EvidenceStatus.recorded,source=src)])
    facts={f.attribute:f for f in roof.facts}
    assert facts["form"].value=="gable"
    assert facts["form"].source.provider=="Test"
    assert facts["replacement date"].status==EvidenceStatus.unknown
