"""Report generation tests use explicitly synthetic unit fixtures, never live demonstrations."""
from app.models.network import ReportSnapshot, ConnectivityResult
from app.reports.generator import generate_report_from_snapshot


def test_snapshot_roundtrip_and_pdf_output(tmp_path):
    snapshot = ReportSnapshot(results=[ConnectivityResult(target='127.0.0.1', response_times_ms=[0, None])],
                              warnings=['Synthetic unit fixture: <escape & wrap>'])
    restored = ReportSnapshot.model_validate_json(snapshot.model_dump_json())
    assert restored.results[0].packet_loss_percent == 50
    path = generate_report_from_snapshot(restored, output_dir=tmp_path / 'reports')
    assert path.parent == tmp_path / 'reports'
    assert path.read_bytes().startswith(b'%PDF-')
    assert path.read_bytes().rstrip().endswith(b'%%EOF')
    assert path.stat().st_size > 1000
    another = generate_report_from_snapshot(restored, output_dir=path.parent)
    assert another != path and path.exists()
